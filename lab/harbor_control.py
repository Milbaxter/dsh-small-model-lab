"""Pinned, sequential official Harbor trials; never forwards independent feedback to proposers."""
import argparse
import asyncio
import fcntl
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tomllib
from urllib.parse import urlparse
import urllib.request

from lab.budget import Ledger
from lab.metrics import trace_metrics

ROOT=Path(__file__).resolve().parents[1]
HARBOR_COMMIT='a38eb549b5f3c33d16ccd5c51734b0defff8399e'
COMPARISON_FILES=('package-lock.json','requirements.lock','lab/profiles.py','lab/trial_worker.py',
    'lab/worker.py','lab/harbor_worker.py','lab/harbor_agent.py','lab/gateway.py','lab/budget.py')


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def file_digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()


def checkout(path):
    if subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True):
        raise ValueError('Scored inputs must come from clean pinned checkouts')
    return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()


def validate_bundle(bundle):
    with tarfile.open(bundle,'r:gz') as archive:
        for name in COMPARISON_FILES:
            member=archive.extractfile('lab/'+name)
            if member is None or hashlib.sha256(member.read()).hexdigest()!=file_digest(ROOT/name):
                raise ValueError('Exported runtime is stale: rebuild before freezing a scored manifest')


def private_gateway(url):
    parsed=urlparse(url)
    try:address=ipaddress.ip_address(parsed.hostname)
    except (ValueError,TypeError):raise ValueError('Gateway must use the dedicated worker Docker bridge IPv4')
    if (parsed.scheme!='http' or parsed.path!='/v1' or parsed.port!=18080 or parsed.username
        or parsed.password or parsed.query or parsed.fragment or address.version!=4
        or not address.is_private or address.is_loopback or address.is_unspecified):
        raise ValueError('Gateway must bind a private Docker bridge address on port 18080')
    return str(address)


def prepare(lock, dataset, bundle, gateway, evaluator, state, model):
    from harbor.models.trial.config import TrialConfig
    dataset=Path(dataset).resolve();bundle=Path(bundle).resolve();state=Path(state).resolve()
    private_gateway(gateway)
    if checkout(dataset)!=lock['dataset_commit']:raise ValueError('Dataset differs from freeze')
    if checkout(evaluator)!=HARBOR_COMMIT:raise ValueError('Harbor evaluator differs from pin')
    actual={p.parent.name:file_digest(p) for p in (dataset/'tasks').glob('*/task.toml')}
    if actual!={t['id']:t['task_config_sha256'] for t in lock['tasks']}:
        raise ValueError('Official task coverage/configuration differs from freeze')
    for task in lock['tasks']:
        config=tomllib.loads((dataset/'tasks'/task['id']/'task.toml').read_text());e=config['environment']
        expected={'cpus':e.get('cpus',1),'memory_mib':e.get('memory_mb',2048),'gpus':e.get('gpus',0),
            'storage_mib':e.get('storage_mb',10240),'agent_timeout_sec':config.get('agent',{}).get('timeout_sec')}
        if any(task.get(k)!=v for k,v in expected.items()):raise ValueError('Frozen resource metadata was changed')
    if (lock['max_required_cpus']!=3*max(t['cpus'] for t in lock['tasks'])
        or lock['max_required_memory_mib']!=3*max(t['memory_mib'] for t in lock['tasks'])):
        raise ValueError('Full-suite resource preflight metadata was changed')
    if lock['k']!=5 or any(t['gpus'] for t in lock['tasks']):
        raise ValueError('This controller implements the full five-repeat CPU-only protocol')
    validate_bundle(bundle)
    conditions={'dataset_commit':lock['dataset_commit'],'evaluator_commit':HARBOR_COMMIT,
        'lab_commit':checkout(ROOT),'runtime_bundle_sha256':file_digest(bundle),'model':model,
        'comparison_runtime':{name:file_digest(ROOT/name) for name in COMPARISON_FILES},
        'permission_mode':'danger-full-access','max_requests':64,'max_tokens':600000,
        'resource_multiplier':lock['minimum_resource_multiplier'],
        'score_label':'Full official suite with predeclared lab inference budgets; not a leaderboard-equivalent run'}
    trials=[]
    def add(task,arm,repetition):
        oracle=arm=='oracle'
        timeout=task['agent_timeout_sec']
        if not isinstance(timeout,(float,int)) or not math.isfinite(timeout) or timeout<=0:
            raise ValueError('Official task needs a finite positive agent timeout')
        multiplier=conditions['resource_multiplier']
        if multiplier!=3:raise ValueError('Resource multiplier must match the frozen lab protocol')
        environment={'type':'docker','delete':True,'override_cpus':math.ceil(multiplier*task['cpus']),
            'override_memory_mb':math.ceil(multiplier*task['memory_mib']),
            'cpu_enforcement_policy':'limit','memory_enforcement_policy':'limit'}
        name=digest([conditions,task['id'],arm,repetition])[:24]
        agent={'name':'oracle'} if oracle else {'import_path':'lab.harbor_agent:DSHAgent',
            'model_name':model['model'],'kwargs':{'arm':arm,'repetition':repetition,
            'bundle':str(bundle),'gateway':gateway,'wall_seconds':timeout,
            'max_requests':conditions['max_requests'],'max_tokens':conditions['max_tokens'],'model_config':model}}
        config=TrialConfig.model_validate({'task':{'path':str(dataset/'tasks'/task['id'])},
            'trial_name':name,'trials_dir':str(state/'trials'),'agent':agent,'environment':environment})
        # Commit/bundle identities also contain candidate policy text. Retain
        # them as provenance, but compare the shared inference machinery so a
        # later isolated policy edit can still use the original baseline.
        common={k:v for k,v in conditions.items() if k not in ('lab_commit','runtime_bundle_sha256')}
        fingerprint=digest({**common,'task':task,'repetition':repetition,'environment':environment})
        trials.append({'task_id':task['id'],'arm':arm,'repetition':repetition,
            'evaluation_fingerprint':fingerprint,'config':config.model_dump(mode='json')})
    # Complete oracle validation before any paid model evaluation.
    for task in lock['tasks']:add(task,'oracle',0)
    arms=['standard','standard+autonomy-policy']
    for repetition in range(lock['k']):
        for index,task in enumerate(lock['tasks']):
            order=arms if (index+repetition)%2==0 else list(reversed(arms))
            for arm in order:add(task,arm,repetition)
    return {'lock':lock,'conditions':conditions,'dataset':str(dataset),'evaluator':str(Path(evaluator).resolve()),
        'bundle':str(bundle),'gateway':gateway,'state':str(state),'trials':trials}


def normalize(result,trial,manifest,audit_dir):
    """Read Harbor's official reward and cross-check controller-owned usage traces."""
    from harbor.models.trial.result import TrialResult
    official=TrialResult.model_validate(result)
    if official.config.model_dump(mode='json')!=trial['config']:
        raise ValueError('Harbor result does not match the frozen trial configuration')
    if not official.finished_at or not official.verifier or not official.verifier.finished_at:
        raise ValueError('Official verifier has not completed')
    rewards=official.verifier_result.rewards if official.verifier_result else None
    if not rewards or set(rewards)!={'reward'} or rewards['reward'] not in (0,1):
        raise ValueError('Expected the official binary reward')
    exception=official.exception_info.exception_type if official.exception_info else None
    if exception and exception!='AgentTimeoutError':
        raise ValueError('Infrastructure or unclassified agent error; preserve result for review')
    if trial['arm']=='oracle':
        if exception or rewards['reward']!=1:raise ValueError('Official oracle validation failed')
        return {'oracle_passed':True,'task_id':trial['task_id']}
    agent=official.agent_result
    metadata=agent.metadata if agent else None
    if not metadata or metadata.get('arm')!=trial['arm'] or metadata.get('repetition')!=trial['repetition']:
        raise ValueError('Agent identity does not match the frozen trial')
    if metadata.get('runtime_bundle_sha256')!=manifest['conditions']['runtime_bundle_sha256']:
        raise ValueError('Agent runtime differs from freeze')
    trace=Path(audit_dir)/'runs'/(Ledger.digest(metadata['gateway_run_id'])+'.jsonl')
    usage=trace_metrics(trace)
    complete=usage['requests']>0 and usage['requests']==usage['accounted_requests']
    if not complete or usage['upstream_errors'] or not metadata.get('accounting_complete'):
        raise ValueError('Independent usage accounting is incomplete or upstream failed')
    if (agent.n_input_tokens!=usage['prompt_tokens'] or agent.n_output_tokens!=usage['completion_tokens']
        or agent.cost_usd!=usage['cost_usd']):raise ValueError('Harbor usage differs from trusted gateway trace')
    return {'task_id':trial['task_id'],'repetition':trial['repetition'],'arm':trial['arm'],
        'dataset_commit':manifest['lock']['dataset_commit'],'verifier':'harbor-official',
        'evaluation_label':manifest['conditions']['score_label'],
        'evaluation_fingerprint':trial['evaluation_fingerprint'],'reward':rewards['reward'],
        'accounting_complete':True,'tokens':usage['prompt_tokens']+usage['completion_tokens'],
        'cost_usd':usage['cost_usd'],'agent_timeout':exception=='AgentTimeoutError',
        'official_result_sha256':digest(result),'gateway_trace_sha256':file_digest(trace)}


def preflight(manifest):
    import harbor
    from importlib.metadata import distribution
    evaluator=Path(manifest['evaluator']).resolve()
    # Verify the loaded Python evaluator, not merely an unused nearby checkout.
    if not Path(harbor.__file__).resolve().is_relative_to(evaluator):
        installed=distribution('harbor')
        origin=json.loads(installed.read_text('direct_url.json') or '{}')
        if (origin.get('vcs_info',{}).get('commit_id')!=HARBOR_COMMIT
            or Path(harbor.__file__).resolve()!=Path(installed.locate_file('harbor/__init__.py')).resolve()):
            raise ValueError('Install Harbor from the pinned evaluator commit before scoring')
    if checkout(ROOT)!=manifest['conditions']['lab_commit']:raise ValueError('Controller source changed')
    if checkout(manifest['dataset'])!=manifest['lock']['dataset_commit']:raise ValueError('Dataset changed')
    if checkout(manifest['evaluator'])!=HARBOR_COMMIT:raise ValueError('Evaluator changed')
    if file_digest(manifest['bundle'])!=manifest['conditions']['runtime_bundle_sha256']:
        raise ValueError('Runtime bundle changed')
    rebuilt=prepare(manifest['lock'],manifest['dataset'],manifest['bundle'],manifest['gateway'],
        manifest['evaluator'],manifest['state'],manifest['conditions']['model'])
    if rebuilt!=manifest:raise ValueError('Frozen execution manifest was changed or is incomplete')
    if not Path('/proc/meminfo').exists():raise ValueError('Scored runs require the dedicated Linux UpCloud worker')
    total=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemTotal:')))//1024
    cpus=os.cpu_count() or 0
    lock=manifest['lock']
    if cpus<lock['max_required_cpus'] or total<lock['max_required_memory_mib']+1024:
        raise ValueError('Worker cannot fit the full frozen suite at the declared resources')
    if shutil.disk_usage(manifest['state']).free<60*1024**3:
        raise ValueError('Dedicated worker needs at least 60 GiB free before the full suite')
    ip=private_gateway(manifest['gateway'])
    bridge=json.loads(subprocess.check_output(['docker','network','inspect','bridge'],text=True))[0]
    if ip not in [c.get('Gateway') for c in bridge['IPAM']['Config']]:
        raise ValueError('Gateway address is not this worker Docker bridge')
    # A healthy endpoint alone does not prove the paid route is privately bound.
    gateway=json.loads(subprocess.check_output(['docker','inspect',
        'dsh-small-model-benchmark-gateway-1'],text=True))[0]
    bindings=gateway['NetworkSettings']['Ports'].get('8000/tcp')
    if bindings!=[{'HostIp':ip,'HostPort':'18080'}]:
        raise ValueError('Budget gateway must publish only on the private bridge address')
    with urllib.request.urlopen(manifest['gateway'].removesuffix('/v1')+'/health',timeout=5) as response:
        if response.status!=200:raise ValueError('Budget gateway is not healthy')


async def run(manifest):
    from harbor.models.trial.config import TrialConfig
    from harbor.trial.trial import Trial
    state=Path(manifest['state']);state.mkdir(parents=True,exist_ok=True)
    with (state/'controller.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        preflight(manifest)
        normalized=[]
        for trial in manifest['trials']:
            config=TrialConfig.model_validate(trial['config'])
            folder=config.trials_dir/config.trial_name;result_path=folder/'result.json'
            if result_path.exists():result=json.loads(result_path.read_text())
            else:
                if folder.exists():raise ValueError('Interrupted trial requires inspection; do not silently rerun it')
                result=(await (await Trial.create(config)).run()).model_dump(mode='json')
            row=normalize(result,trial,manifest,ROOT/'.local/bench-audit')
            normalized.append(row)
            target=state/'normalized.json';temporary=target.with_suffix('.tmp')
            temporary.write_text(json.dumps(normalized,indent=2)+'\n');temporary.replace(target)
            print(json.dumps({'completed':len(normalized),'expected':len(manifest['trials'])}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    for name in ('lock','dataset','bundle','evaluator','state','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--gateway',required=True)
    r=sub.add_parser('run');r.add_argument('--manifest',type=Path,required=True)
    r=sub.add_parser('report');r.add_argument('--manifest',type=Path,required=True)
    r.add_argument('--champion',choices=('standard','standard+autonomy-policy'),required=True)
    r.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='run':asyncio.run(run(json.loads(args.manifest.read_text())))
    elif args.command=='report':
        from lab.terminal_report import summarize,markdown
        manifest=json.loads(args.manifest.read_text())
        rows=json.loads((Path(manifest['state'])/'normalized.json').read_text())
        if len(rows)!=len(manifest['trials']):raise ValueError('Full execution has not completed')
        variants=[{'name':arm,'iteration':i,'rows':[r for r in rows if r.get('arm')==arm]}
            for i,arm in enumerate(('standard','standard+autonomy-policy'))]
        report=summarize(manifest['lock'],variants,args.champion)
        args.output.write_text(markdown(report))
        args.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    else:
        manifest=prepare(json.loads(args.lock.read_text()),args.dataset,args.bundle,args.gateway,
            args.evaluator,args.state,json.loads((ROOT/'config/openrouter.json').read_text()))
        with args.output.open('x') as f:f.write(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps({'trials':len(manifest['trials']),'manifest_sha256':digest(manifest)}))


if __name__=='__main__':main()

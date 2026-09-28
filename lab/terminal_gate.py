"""Freeze Terminal-Bench metadata and compare official verifier outcomes, never task text."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

from lab.statistics import paired_change


def freeze(dataset, target, version):
    dataset=Path(dataset).resolve()
    if subprocess.check_output(['git','-C',str(dataset),'status','--porcelain'],text=True):
        raise ValueError('The official dataset checkout must be clean')
    commit=subprocess.check_output(['git','-C',str(dataset),'rev-parse','HEAD'],text=True).strip()
    tasks=sorted((dataset/'tasks').glob('*/task.toml'))
    if not tasks:raise ValueError('No official tasks found')
    rows=[]
    for path in tasks:
        config=tomllib.loads(path.read_text());e=config['environment']
        rows.append({'id':path.parent.name,'task_config_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'cpus':e.get('cpus',1),'memory_mib':e.get('memory_mb',2048),'gpus':e.get('gpus',0),
            'storage_mib':e.get('storage_mb',10240),'agent_timeout_sec':config.get('agent',{}).get('timeout_sec')})
    record={'benchmark':'Terminal-Bench','version':version,'dataset_commit':commit,'tasks':rows,
            'k':5,'baseline':'standard','baseline_policy':'frozen original plain DSH, shared provider/context settings',
            'selection':'all official tasks; no filtering by scores, prompts, categories or resources',
            'proposer_access':'none','minimum_resource_multiplier':3,
            'max_required_cpus':3*max(r['cpus'] for r in rows),
            'max_required_memory_mib':3*max(r['memory_mib'] for r in rows)}
    target=Path(target)
    with target.open('x') as f:f.write(json.dumps(record,indent=2)+'\n')
    return record


def compare(lock, baseline, candidate, *, iteration=1):
    """Normalized records must originate from official Harbor result.json rewards."""
    required={(t['id'],r) for t in lock['tasks'] for r in range(lock['k'])}
    def scores(rows):
        values={}
        for row in rows:
            key=(row['task_id'],row['repetition'])
            if key in values:raise ValueError('Duplicate task/repetition')
            if row.get('dataset_commit')!=lock['dataset_commit']:raise ValueError('Dataset changed')
            if row.get('verifier')!='harbor-official':raise ValueError('Unofficial grading')
            if row.get('infrastructure_error') or not row.get('accounting_complete'):
                raise ValueError('Independent gate has infrastructure or accounting gaps')
            values[key]=row['reward']
        if set(values)!=required:raise ValueError('Full frozen task coverage is required')
        return values
    b,c=scores(baseline),scores(candidate)
    # Report standard 95% CIs; use an alpha-spending bound for repeated selection.
    result=paired_change(b,c,repetitions=lock['k'])
    alpha=.05/(iteration*(iteration+1))
    from random import Random
    from lab.statistics import quantile
    rng=Random(1729);tasks=sorted({t for t,r in b});diff={t:sum(c[t,r]-b[t,r] for r in range(lock['k']))/lock['k'] for t in tasks}
    draws=[sum(diff[rng.choice(tasks)] for _ in tasks)/len(tasks) for _ in range(20000)]
    lower=quantile(draws,alpha/2)
    result.update(iteration=iteration,selection_alpha=alpha,selection_lower_bound_percentage_points=100*lower,
                  independent_gate_passed=lower>0)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--lock',type=Path,required=True)
    parser.add_argument('--version',required=True)
    args=parser.parse_args()
    result=freeze(args.dataset,args.lock,args.version)
    print(json.dumps({'tasks':len(result['tasks']),'version':result['version'],
        'max_required_cpus':result['max_required_cpus'],'max_required_memory_mib':result['max_required_memory_mib']}))


if __name__=='__main__':main()

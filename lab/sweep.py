"""Resumable, single-worker private benchmark controller. Run on the Docker host."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid

from lab.budget import Ledger
from lab.metrics import failure_tag, trace_metrics

ROOT=Path(__file__).resolve().parents[1]
IMAGE='dsh-small-model-lab-openrouter-runner:latest'
NETWORK='dsh-small-model-benchmark_inference'


def write_files(root, files):
    for name,text in files.items():
        target=root/name
        if name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Invalid task path')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text)


def grade(task, workspace, image=IMAGE):
    hidden=task['hidden']
    if 'cases' in hidden:
        request={'kind':'code','inputs':[pair[0] for pair in hidden['cases']]}
    else:
        request={'kind':'files','files':list(hidden['files'])}
    name='dsh-grade-'+uuid.uuid4().hex
    cmd=['docker','run','--rm','-i','--name',name,'--network','none','--read-only',
         '--cap-drop=ALL','--security-opt=no-new-privileges','--cpus=.75','--memory=384m',
         '--pids-limit=64','--tmpfs','/tmp:size=32m','--mount',f'type=bind,src={workspace},dst=/workspace,readonly',
         '--entrypoint','python',image,'-B','-m','lab.grade_worker']
    # Expected answers NEVER enter the container executing submitted code.
    try:
        result=subprocess.run(cmd,input=json.dumps(request),text=True,capture_output=True,timeout=30)
        if result.returncode!=0 or len(result.stdout)>4_000_000:return False
        response=json.loads(result.stdout)
        if 'cases' in hidden:
            return response=={'results':[{'value':expected,'unchanged':True} for _,expected in hidden['cases']]}
        return response=={'files':hidden['files']}
    except (subprocess.TimeoutExpired,ValueError,OSError):
        return False
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)


def run_worker(run_dir, task, model, arm, token, image=IMAGE):
    name='dsh-trial-'+run_dir.name
    env={**os.environ,'LAB_VLLM_KEY':token}
    cmd=['docker','run','--rm','-i','--name',name,'--network',NETWORK,'--read-only',
         '--cap-drop=ALL','--security-opt=no-new-privileges','--cpus=.75','--memory=384m',
         '--oom-score-adj=800','--pids-limit=128','--tmpfs','/tmp:exec,size=128m',
         '--mount',f'type=bind,src={run_dir},dst=/run','-e','LAB_VLLM_KEY',
         '--entrypoint','python',image,'-m','lab.trial_worker']
    deadline=time.monotonic()+task['budget']['wall_seconds']
    messages=queue.Queue(); status='error'; stages_completed=0
    # Controller output is outside the actor mount, including its process exit status.
    stderr_path=run_dir.parent/(run_dir.name+'.stderr')
    with stderr_path.open('w') as errors:
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,
                                 text=True,bufsize=1,env=env)
        def reader():
            for line in process.stdout:messages.put(line)
            messages.put(None)
        thread=threading.Thread(target=reader,daemon=True);thread.start()
        try:
            process.stdin.write(json.dumps({'model':model,'arm':arm})+'\n');process.stdin.flush()
            for index,stage in enumerate(task['stages']):
                process.stdin.write(json.dumps(stage)+'\n');process.stdin.flush()
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError()
                    try:line=messages.get(timeout=min(remaining,1))
                    except queue.Empty:continue
                    if line is None:raise RuntimeError('Worker ended before completing stages')
                    try:message=json.loads(line)
                    except ValueError:continue
                    if message.get('stage_complete')==index:
                        stages_completed+=1;break
            process.stdin.write('{"end":true}\n');process.stdin.flush();process.stdin.close()
            code=process.wait(timeout=max(1,deadline-time.monotonic()))
            status='completed' if code==0 else 'error'
        except (TimeoutError,subprocess.TimeoutExpired):status='timeout'
        except (BrokenPipeError,OSError,RuntimeError):status='error'
        finally:
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
            if process.poll() is None:process.kill()
            process.wait(timeout=10);thread.join(timeout=2)
    return status,stages_completed


def open_db(path):
    db=sqlite3.connect(path)
    db.execute('''CREATE TABLE IF NOT EXISTS trials (
        trial_key TEXT PRIMARY KEY, task_id TEXT, split TEXT, family TEXT, archetype TEXT,
        arm TEXT, model TEXT, repetition INTEGER, run_id TEXT, status TEXT,
        result TEXT, created REAL, updated REAL)''')
    db.commit();return db


def memory_available():
    path=Path('/proc/meminfo')
    if not path.exists():return None
    return int(next(l.split()[1] for l in path.read_text().splitlines() if l.startswith('MemAvailable:')))//1024


def reserved_memory_headroom():
    """Respect other tasks' containers without stopping or modifying them."""
    path=Path('/proc/meminfo')
    if not path.exists():return None
    total=int(next(l.split()[1] for l in path.read_text().splitlines() if l.startswith('MemTotal:')))//1024
    ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
    if not ids:return total
    containers=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
    reserved=sum((c['HostConfig']['Memory']//1024**2) if c['HostConfig']['Memory'] else total for c in containers)
    return total-reserved


def task_hash(task):
    return hashlib.sha256(json.dumps(task,sort_keys=True).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank',type=Path,required=True)
    parser.add_argument('--split',choices=('dev','heldout','transfer','all'),default='dev')
    parser.add_argument('--arms',nargs='+',default=['standard'])
    parser.add_argument('--repetitions',type=int,default=5)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--family')
    parser.add_argument('--per-family',type=int,help='Calibration-only balanced cap per family')
    parser.add_argument('--state',type=Path,default=ROOT/'.local/benchmark')
    parser.add_argument('--config',type=Path,default=ROOT/'config/openrouter.json')
    parser.add_argument('--min-free-memory-mib',type=int,default=768)
    parser.add_argument('--wait-capacity',action='store_true')
    args=parser.parse_args()
    if args.repetitions<1 or args.repetitions>5:parser.error('Repetitions must be 1..5')
    args.state.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=(args.state/'controller.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('A sweep controller already owns this state')
    model=json.loads(args.config.read_text())
    model['max_request_bytes']=262144
    image_id=subprocess.check_output(['docker','image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip()
    bank_commit=subprocess.check_output(['git','-C',str(args.bank),'rev-parse','HEAD'],text=True).strip()
    code_commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(args.bank),'status','--porcelain'],text=True)
    if dirty:raise SystemExit('Task bank must be committed before a scored sweep')
    tasks=[json.loads(p.read_text()) for p in sorted((args.bank/'tasks').glob('*.json'))]
    tasks=[t for t in tasks if (args.split=='all' or t['split']==args.split) and (not args.family or t['family']==args.family)]
    if args.per_family:
        counts={}; selected=[]
        for task in tasks:
            family=task['family']
            if counts.get(family,0)<args.per_family:
                selected.append(task);counts[family]=counts.get(family,0)+1
        tasks=selected
    if args.limit:tasks=tasks[:args.limit]
    ledger=Ledger(ROOT/'.local/bench-audit/budget.sqlite')
    db=open_db(args.state/'trials.sqlite')
    runs=args.state/'runs';runs.mkdir(exist_ok=True)
    completed=0
    for rep in range(args.repetitions):
        for task in tasks:
            for arm in args.arms:
                config={**model,'seed':1729+rep}
                identity={'task_hash':task_hash(task),'bank_commit':bank_commit,'image':image_id,
                          'arm':arm,'config':config,'repetition':rep}
                key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
                prior=db.execute('SELECT run_id,status FROM trials WHERE trial_key=?',(key,)).fetchone()
                if prior and prior[1]=='complete':continue
                if prior:
                    running=subprocess.run(['docker','inspect','--format','{{.State.Running}}','dsh-trial-'+prior[0]],capture_output=True,text=True)
                    if running.returncode==0 and running.stdout.strip()=='true':
                        raise SystemExit('Prior trial is still live; inspect it before resuming')
                    # Preserve failed/crashed attempt files and its reserved spend.
                    ledger.close(prior[0])
                last_wait_notice=0
                while True:
                    available=memory_available()
                    reserved=reserved_memory_headroom()
                    issue=None
                    if available is not None and available<args.min_free_memory_mib:
                        issue=f'Only {available} MiB currently available'
                    if reserved is not None and reserved<512:
                        issue=f'Other containers reserve the host; {reserved} MiB unreserved'
                    if shutil.disk_usage(args.state).free<2*1024**3:
                        issue='Less than 2 GiB disk headroom'
                    if not issue:break
                    if not args.wait_capacity:raise SystemExit(issue)
                    if time.monotonic()-last_wait_notice>=60:
                        print(json.dumps({'status':'waiting_capacity','reason':issue}),flush=True)
                        last_wait_notice=time.monotonic()
                    time.sleep(10)
                run_id=uuid.uuid4().hex;run_dir=runs/run_id;run_dir.mkdir(mode=0o700)
                workspace=run_dir/'workspace';workspace.mkdir();write_files(workspace,task['workspace'])
                budget=task['budget']
                token=ledger.register(run_id,max_requests=budget['max_requests'],max_tokens=budget['max_tokens'],
                                      wall_seconds=budget['wall_seconds']+30,config=config)
                now=time.time()
                db.execute('INSERT OR REPLACE INTO trials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (key,task['task_id'],task['split'],task['family'],task['archetype'],arm,model['model'],rep,run_id,'running',None,now,now));db.commit()
                started=time.monotonic()
                try:status,stages=run_worker(run_dir,task,config,arm,token,image_id)
                finally:ledger.close(run_id)
                passed=status=='completed' and stages==len(task['stages']) and grade(task,workspace,image_id)
                trace=ROOT/'.local/bench-audit/runs'/(Ledger.digest(run_id)+'.jsonl')
                metrics=trace_metrics(trace)
                tag=failure_tag(status,passed,metrics,budget['max_requests'])
                private={k:v for k,v in metrics.items() if k.startswith('_')}
                metrics={k:v for k,v in metrics.items() if not k.startswith('_')}
                compactions=0
                for path in (run_dir/'home/sessions').rglob('*.jsonl'):
                    for line in path.read_text(errors='replace').splitlines():
                        try:
                            event=json.loads(line)
                            if event.get('type')=='compaction/summary':compactions+=1
                        except ValueError:pass
                result={'passed':bool(passed),'failure_tag':tag,'status':status,'metrics':metrics,
                        'wall_seconds':time.monotonic()-started,'stages_completed':stages,'compaction_events_observed':compactions,
                        'requires_compaction':task.get('requires_compaction',False),'identity':identity,'code_commit':code_commit,
                        'trace':str(trace),'run_dir':str(run_dir),'minimum_resources':task['minimum_resources'],
                        'allocated_resources':{'cpus':.75,'memory_mib':384}}
                # Scores are provisional until controller accounting and family coverage checks pass.
                result['accounting_complete']=metrics['requests']==metrics['accounted_requests']
                db.execute('UPDATE trials SET status=?,result=?,updated=? WHERE trial_key=?',('complete',json.dumps(result),time.time(),key));db.commit()
                (args.state/(run_id+'.json')).write_text(json.dumps(result,indent=2))
                completed+=1
                print(json.dumps({'completed':completed,'split':task['split'],'family':task['family'],'arm':arm,'repetition':rep,'passed':bool(passed),'tag':tag,'cost_usd':metrics['cost_usd']}),flush=True)
    db.close()


if __name__=='__main__':main()

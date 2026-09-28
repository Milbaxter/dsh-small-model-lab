"""Build dev-only packets and validate one bounded policy mutation. No hidden feedback."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def development_packet(bank, db_path, *, champion, limit=8):
    tasks={}
    for path in (Path(bank)/'tasks').glob('*.json'):
        task=json.loads(path.read_text())
        if task['split']=='dev':tasks[task['task_id']]=task
    db=sqlite3.connect(db_path);db.row_factory=sqlite3.Row
    selected=[];seen=set()
    for raw in db.execute("SELECT * FROM trials WHERE status='complete' AND split='dev' AND arm=? ORDER BY updated DESC",(champion,)):
        row=dict(raw);result=json.loads(row['result'])
        if result['passed'] or row['task_id'] in seen:continue
        task=tasks.get(row['task_id'])
        if task is None:raise ValueError('Dev result is not in the pinned dev bank')
        trace_path=Path(result['trace'])
        exchanges=[]
        if trace_path.exists():
            # These are the agent-visible exchanges recorded by the trusted gateway.
            for line in trace_path.read_text().splitlines():
                event=json.loads(line)
                if event.get('kind')=='request':exchanges=event['payload'].get('messages',[])
        selected.append({'task_id':task['task_id'],'family':task['family'],
            'instructions':[s['instruction'] for s in task['stages']],
            'visible_workspace':task['workspace'],'failure_tag':result['failure_tag'],
            'metrics':result['metrics'],'last_exchanges':exchanges[-8:]})
        seen.add(task['task_id'])
        if len(selected)>=limit:break
    db.close()
    packet={'split':'dev','champion':champion,'examples':selected,
        'allowed_mutation':'one general workflow policy, at most 450 words; no tools, routing, budget or grader changes',
        'forbidden':'task-specific names, files, values, answers or special-case heuristics; hidden or Terminal-Bench feedback'}
    # The exporter builds a whitelist, not a redacted copy of private task objects.
    return packet


def leakage_scan(policy, dev_tasks):
    words=re.findall(r"[a-z0-9]+",policy.lower())
    if not 20<=len(words)<=450:raise ValueError('Policy must contain 20..450 words')
    candidate_grams={' '.join(words[i:i+6]) for i in range(len(words)-5)}
    reasons=[]
    for task in dev_tasks:
        if task['split']!='dev':raise ValueError('This development leakage check accepts dev tasks only')
        visible=json.dumps({'instructions':[s['instruction'] for s in task['stages']], 'workspace':task['workspace']})
        identifiers=set(re.findall(r'\b[a-zA-Z]+-[a-f0-9]{8,}\b',visible))
        names=set(task['workspace'])
        if any(name in policy for name in names|identifiers):reasons.append('task-specific identifier or file path')
        tokens=re.findall(r'[a-z0-9]+',' '.join(s['instruction'] for s in task['stages']).lower())
        grams={' '.join(tokens[i:i+6]) for i in range(len(tokens)-5)}
        if grams&candidate_grams:reasons.append('verbatim task instruction overlap')
    return {'passed':not reasons,'candidate_sha256':digest(policy),'reasons':sorted(set(reasons))}


def validate_proposal(raw):
    required={'target_failure','hypothesis','mechanism','disconfirmation','policy'}
    if set(raw)!=required:raise ValueError('Proposer must return exactly the bounded proposal fields')
    if any(not isinstance(v,str) or not v.strip() for v in raw.values()):raise ValueError('Proposal fields must be nonempty text')
    for key in required-{'policy'}:
        if len(raw[key])>2000:raise ValueError('Proposal explanation is oversized')
    if len(raw['policy'])>6000:raise ValueError('Policy text is oversized')
    return raw


def policy_module(policy):
    """Treat the model's proposal strictly as text, never executable JavaScript."""
    return ('export const name = "lab-candidate-policy";\n'
            'export const inject = ["systemPrompt"];\n'
            'export function apply(ctx) {\n'
            '  ctx.systemPrompt.section({name:"lab:candidate-policy",order:10300,text:'+
            json.dumps(policy,ensure_ascii=True)+'});\n}\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank',type=Path,required=True)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--champion',default='standard')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    packet=development_packet(args.bank,args.db,champion=args.champion)
    if not packet['examples']:raise SystemExit('No dev failure evidence available for a proposal')
    text=json.dumps(packet,indent=2)
    args.output.write_text(text+'\n');args.output.chmod(0o600)
    print(json.dumps({'examples':len(packet['examples']),'packet_sha256':digest(text)}))


if __name__=='__main__':main()

"""Aggregate private sweep results without exporting tasks, grader details, or traces."""
from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path
import random
import sqlite3

from lab.statistics import paired_change, quantile


def summarize(rows, repetitions=5, expected_tasks=None):
    groups=defaultdict(list)
    for row in rows:groups[row['arm'],row['split'],row['model']].append(row)
    report={'kind':'private_suite','provisional':False,'cells':[],'comparisons':[]}
    for (arm,split,model),items in sorted(groups.items()):
        by_task=defaultdict(list)
        for item in items:by_task[item['task_id']].append(item)
        complete=all(len(v)==repetitions and {r['repetition'] for r in v}==set(range(repetitions)) for v in by_task.values())
        if expected_tasks is not None:complete=complete and len(by_task)==expected_tasks
        accounting=all(i['result']['accounting_complete'] for i in items)
        means=[sum(i['result']['passed'] for i in v)/len(v) for v in by_task.values()]
        rng=random.Random(1729)
        boot=[sum(rng.choice(means) for _ in means)/len(means) for _ in range(10000)]
        solved=sum(i['result']['passed'] for i in items)
        tokens=sum(i['result']['metrics']['prompt_tokens']+i['result']['metrics']['completion_tokens'] for i in items)
        faults=Counter(i['result']['failure_tag'] for i in items if i['result']['failure_tag'])
        context_items=[i for i in items if i['result'].get('requires_compaction')]
        context_valid=arm=='sdk-minimal' or all(i['result'].get('compaction_events_observed',0)>0 for i in context_items)
        cell={'arm':arm,'split':split,'model':model,'tasks':len(by_task),'runs':len(items),
              'success_pct':100*solved/len(items),'task_cluster_95ci_pct':[100*quantile(boot,.025),100*quantile(boot,.975)],
              'tokens_per_solve':tokens/solved if solved else None,
              'cost_usd':sum(i['result']['metrics']['cost_usd'] for i in items),
              'failure_tags':dict(faults),'complete_repetitions':complete,'accounting_complete':accounting,
              'context_compaction_coverage_valid':context_valid,
              'infrastructure_errors':sum(i['result']['failure_tag']=='INFRA' for i in items)}
        report['cells'].append(cell)
        if not complete or not accounting or not context_valid:report['provisional']=True
    for (arm,split,model),items in groups.items():
        if arm=='standard':continue
        plain=groups.get(('standard',split,model))
        if not plain:continue
        b={(i['task_id'],i['repetition']):int(i['result']['passed']) for i in plain}
        c={(i['task_id'],i['repetition']):int(i['result']['passed']) for i in items}
        clusters={i['task_id']:i['archetype'] for i in items}
        try:
            effect=paired_change(b,c,repetitions=repetitions)
            sensitivity=paired_change(b,c,repetitions=repetitions,clusters=clusters)
        except ValueError:
            report['provisional']=True;continue
        report['comparisons'].append({'reference':'standard','candidate':arm,'split':split,'model':model,
            **effect,'archetype_cluster_sensitivity_95ci_pp':sensitivity['paired_95ci_percentage_points']})
    report['independent_terminal_bench']='not represented by this report; required separately'
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-tasks',type=int)
    args=parser.parse_args()
    db=sqlite3.connect(args.db);db.row_factory=sqlite3.Row
    rows=[]
    for row in db.execute("SELECT * FROM trials WHERE status='complete'"):
        item=dict(row);item['result']=json.loads(item['result']);rows.append(item)
    report=summarize(rows,expected_tasks=args.expected_tasks)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

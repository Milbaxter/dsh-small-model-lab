"""Aggregate complete official comparisons against original DSH and the final champion."""
import argparse
import json
from pathlib import Path

from lab.statistics import paired_change
from lab.terminal_gate import compare


def summarize(lock, variants, champion):
    """Variants contain controller-normalized outcomes, never proposer-generated scores."""
    by_name={v['name']:v for v in variants}
    if len(by_name)!=len(variants):raise ValueError('Duplicate variant')
    if 'standard' not in by_name or champion not in by_name:
        raise ValueError('Original plain DSH and final champion are required')
    attempts=[v['iteration'] for v in variants if v['name']!='standard']
    if sorted(attempts)!=list(range(1,len(attempts)+1)):
        raise ValueError('Include every independent attempt in sequence, including rejected variants')
    baseline=by_name['standard']['rows'];final=by_name[champion]['rows']
    rows=[]
    for variant in variants:
        comparison=compare(lock,baseline,variant['rows'],iteration=max(1,variant['iteration']))
        scores={(r['task_id'],r['repetition']):r['reward'] for r in variant['rows']}
        final_scores={(r['task_id'],r['repetition']):r['reward'] for r in final}
        to_final=paired_change(scores,final_scores,repetitions=lock['k'])
        solved=sum(scores.values())
        if any(r.get('tokens') is None or r.get('cost_usd') is None for r in variant['rows']):
            raise ValueError('Token and cost accounting is required for the final report')
        tokens=sum(r['tokens'] for r in variant['rows'])
        cost=sum(r['cost_usd'] for r in variant['rows'])
        if tokens<0 or cost<0:raise ValueError('Usage cannot be negative')
        rows.append({'variant':variant['name'],'success_pct':comparison['candidate_success_pct'],
            'vs_original_plain_dsh':comparison,'final_champion_vs_this_variant':to_final,
            'tokens_per_solve':tokens/solved if solved else None,'cost_usd':cost})
    return {'benchmark':'Terminal-Bench','version':lock['version'],'dataset_commit':lock['dataset_commit'],
        'reference':'original-plain-dsh','champion':champion,'full_frozen_coverage':True,
        'rows':rows,'relative_change_note':'Undefined when the comparison reference scores zero.'}


def markdown(report):
    lines=[f"Terminal-Bench {report['version']} — final champion: {report['champion']}",'',
        '| Variant | Resolved | Δ vs plain DSH | Relative gain vs plain DSH | Champion gain vs variant | Spend |',
        '|---|---:|---:|---:|---:|---:|']
    def relative(value):return 'undefined' if value is None else f'{value:+.2f}%'
    for row in report['rows']:
        b=row['vs_original_plain_dsh'];c=row['final_champion_vs_this_variant']
        lines.append(f"| {row['variant']} | {row['success_pct']:.2f}% | {b['change_percentage_points']:+.2f} pp | "
            f"{relative(b['relative_change_pct'])} | {relative(c['relative_change_pct'])} | ${row['cost_usd']:.4f} |")
    lines.extend(['','Paired task-cluster 95% confidence intervals (percentage points):',''])
    for row in report['rows']:
        low,high=row['vs_original_plain_dsh']['paired_95ci_percentage_points']
        lines.append(f"- {row['variant']} vs original plain DSH: [{low:+.2f}, {high:+.2f}] pp.")
    lines.extend(['',report['relative_change_note'],''])
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True,help='Controller manifest with lock, variants and champion')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=summarize(**json.loads(args.input.read_text()))
    args.output.write_text(markdown(report))
    args.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()

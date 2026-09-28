"""Fail-closed promotion gate. Missing evidence is never counted as a passing gate."""
from collections import defaultdict
from dataclasses import asdict, dataclass
import json

from lab.statistics import paired_change


@dataclass(frozen=True)
class Protocol:
    repetitions: int = 5
    dev_tasks: int = 40
    heldout_tasks: int = 40
    transfer_tasks: int = 20
    max_token_increase: float = .25
    # No post-hoc 'large gain' exception. A changed threshold requires a new protocol.
    min_transfer_models: int = 2


def normalize(rows, protocol):
    by_key={}
    for row in rows:
        key=(row['model'],row['split'],row['task_id'],row['repetition'])
        if key in by_key:raise ValueError('Duplicate scored trial')
        if row['repetition'] not in range(protocol.repetitions):raise ValueError('Unexpected repetition')
        if type(row['passed']) is not bool:raise ValueError('Outcome must be binary')
        if row.get('infrastructure_error') or not row.get('accounting_complete'):
            raise ValueError('Infrastructure/accounting evidence incomplete')
        if not row.get('evaluation_fingerprint'):
            raise ValueError('Missing pinned evaluation conditions')
        if row['tokens']<0:raise ValueError('Invalid usage')
        by_key[key]=row
    return by_key


def compare_split(champion, candidate, model, split, count, protocol):
    b={k[2:]:v for k,v in champion.items() if k[:2]==(model,split)}
    c={k[2:]:v for k,v in candidate.items() if k[:2]==(model,split)}
    if len(b)!=count*protocol.repetitions or set(b)!=set(c):
        raise ValueError(f'{split}: missing required paired task coverage')
    if len({k[0] for k in b})!=count:raise ValueError(f'{split}: unexpected task count')
    if any(b[k]['evaluation_fingerprint']!=c[k]['evaluation_fingerprint'] for k in b):
        raise ValueError(f'{split}: model, sampling, task or resource conditions differ')
    return paired_change({k:int(v['passed']) for k,v in b.items()},
                         {k:int(v['passed']) for k,v in c.items()},repetitions=protocol.repetitions)


def tokens_per_solve(rows):
    solved=sum(r['passed'] for r in rows)
    return sum(r['tokens'] for r in rows)/solved if solved else None


def decide(*, champion_rows, candidate_rows, control_rows, primary_model,
           leakage, review, terminal_evidence, protocol=Protocol()):
    """Only controller-normalized records belong here, never proposer-supplied scores."""
    checks={};details={};errors=[]
    try:
        champion=normalize(champion_rows,protocol);candidate=normalize(candidate_rows,protocol)
        control=normalize(control_rows,protocol)
        dev=compare_split(champion,candidate,primary_model,'dev',protocol.dev_tasks,protocol)
        heldout=compare_split(champion,candidate,primary_model,'heldout',protocol.heldout_tasks,protocol)
        checks['dev_improves']=dev['change_percentage_points']>0
        checks['heldout_positive_ci']=heldout['paired_95ci_percentage_points'][0]>0
        details.update(dev=dev,heldout=heldout)
        transfer_models={key[0] for key in candidate if key[1]=='transfer'}
        checks['two_model_transfer']=len(transfer_models)>=protocol.min_transfer_models and primary_model in transfer_models
        details['transfer']={}
        for model in sorted(transfer_models):
            effect=compare_split(champion,candidate,model,'transfer',protocol.transfer_tasks,protocol)
            details['transfer'][model]=effect
        checks['no_significant_transfer_regression']=bool(transfer_models) and all(
            d['paired_95ci_percentage_points'][1]>=0 for d in details['transfer'].values())
        matched=compare_split(control,candidate,primary_model,'heldout',protocol.heldout_tasks,protocol)
        checks['beats_matched_budget_control']=matched['paired_95ci_percentage_points'][0]>0
        # The controller must explicitly record a predeclared matched-budget design.
        checks['control_design_verified']=bool(control_rows) and all(r.get('matched_budget_verified') is True for r in control_rows)
        details['matched_budget']=matched
        b=[r for r in champion_rows if r['model']==primary_model and r['split']=='heldout']
        c=[r for r in candidate_rows if r['model']==primary_model and r['split']=='heldout']
        bt,ct=tokens_per_solve(b),tokens_per_solve(c)
        checks['token_pareto']=bt is not None and ct is not None and ct<=bt*(1+protocol.max_token_increase)
        details['heldout_tokens_per_solve']={'champion':bt,'candidate':ct}
    except (ValueError,KeyError,TypeError) as exc:
        errors.append(str(exc));checks['evidence_complete']=False
    checks['leakage_scan_passed']=leakage.get('passed') is True and bool(leakage.get('candidate_sha256'))
    checks['separate_review_passed']=(review.get('decision')=='accept' and review.get('separate_request') is True
        and review.get('model')=='openai/gpt-6-astra' and review.get('candidate_sha256')==leakage.get('candidate_sha256'))
    checks['terminal_independent_gate']=(terminal_evidence.get('independent_gate_passed') is True
        and terminal_evidence.get('candidate_sha256')==leakage.get('candidate_sha256')
        and terminal_evidence.get('reference')=='original-plain-dsh'
        and terminal_evidence.get('full_frozen_coverage') is True)
    promote=bool(checks) and all(checks.values())
    return {'decision':'promote' if promote else ('insufficient_evidence' if errors else 'reject'),
            'checks':checks,'details':details,'errors':errors,'protocol':asdict(protocol)}

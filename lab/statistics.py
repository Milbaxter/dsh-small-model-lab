"""Task-cluster confidence intervals and paired percentage-change reporting."""
from collections import defaultdict
import random


def quantile(values, p):
    s=sorted(values); x=(len(s)-1)*p; i=int(x); f=x-i
    return s[i]*(1-f)+s[min(i+1,len(s)-1)]*f


def paired_change(baseline, candidate, *, repetitions=5, draws=10000, seed=1729, clusters=None):
    """Inputs map (task_id, repetition) to binary scores. Resample tasks, not runs."""
    if not baseline or set(baseline)!=set(candidate):
        raise ValueError('A paired comparison needs identical nonempty task/repetition keys')
    grouped=defaultdict(list)
    for task,rep in baseline:
        if baseline[task,rep] not in (0,1) or candidate[task,rep] not in (0,1):
            raise ValueError('Scores must be binary')
        grouped[task].append(rep)
    if any(set(reps)!=set(range(repetitions)) or len(reps)!=repetitions for reps in grouped.values()):
        raise ValueError('Incomplete or unexpected repetitions')
    differences={task:sum(candidate[task,r]-baseline[task,r] for r in reps)/repetitions for task,reps in grouped.items()}
    task_groups=defaultdict(list)
    for task in differences:task_groups[clusters[task] if clusters else task].append(task)
    units=list(task_groups.values()); rng=random.Random(seed); boot=[]
    for _ in range(draws):
        sampled=[task for _ in units for task in rng.choice(units)]
        boot.append(sum(differences[t] for t in sampled)/len(sampled))
    b=sum(baseline.values())/len(baseline); c=sum(candidate.values())/len(candidate)
    return {'baseline_success_pct':100*b,'candidate_success_pct':100*c,
        'change_percentage_points':100*(c-b),'relative_change_pct':100*(c-b)/b if b else None,
        'paired_95ci_percentage_points':[100*quantile(boot,.025),100*quantile(boot,.975)],
        'tasks':len(grouped),'repetitions':repetitions,'clusters':len(units),'bootstrap_draws':draws,
        'significant_improvement':quantile(boot,.025)>0}

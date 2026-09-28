# Independent Terminal-Bench gate

Terminal-Bench is the independent check requested by the owner. Private tasks
remain the development/calibration suite. A private-suite gain alone cannot
promote an improvement or support a general capability claim.

The fixed reference is plain DSH `standard`, with the same documented model,
small-context settings, resources and budgets used for every candidate. Preserve
this reference throughout the experiment; do not replace it when the champion
changes. Test autonomy-policy and later individual improvements against both this
fixed reference and the current champion. The final report must compare the final
champion directly with the original plain DSH reference.

Pin the official Terminal-Bench dataset and Harbor evaluator before the first
scored run. Use the official task environments and verifiers. Current upstream
release under inspection is Terminal-Bench 4.0.0; resource preflight and the DSH
adapter must pass before starting it. No Terminal-Bench run has completed yet.

For each paired comparison, use five repetitions per task. Report the baseline
and candidate resolution percentages, their percentage-point difference, relative
percentage change, paired task-cluster 95% confidence interval, tokens per solve,
reported model spend and infrastructure failures. If baseline success is zero,
relative percentage change is undefined; report absolute change instead. A
subset or constrained-budget pilot must be labeled as such, never as a full
Terminal-Bench or leaderboard-equivalent score.

The proposer receives no Terminal-Bench tasks, solutions, tests, traces, per-task
outcomes or improvement suggestions derived from its failures. Development uses
private dev feedback only. A gate failure rejects the candidate; it does not
trigger task-specific repair. Freeze candidate source before independent testing.
Account for repeated candidate selection when applying confidence thresholds;
descriptive 95% intervals alone are not permission for unlimited gate attempts.
Publish every attempted independent comparison, including failures, at aggregate
level. Preserve the final champion-versus-original-baseline comparison explicitly.

Promotion requires all private-suite gates plus a positive independent paired
confidence bound. A claim of improvement remains unproven if the sample is too
small, accounting is incomplete, infrastructure changes the task conditions, or
any required gate is missing. Record a no-improvement outcome honestly if that
is what the measurements show.

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
release options inspected are 2.1 and 4.0.0. The CPU-only 2.1 path is prepared;
resource preflight and the DSH adapter must pass before scoring it. No
Terminal-Bench run has completed yet.

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

## Shared-host preflight

Northlight also hosts another independently running lab. Do not inspect or reuse
its task bank, candidate reasoning or benchmark failures. Do not terminate its
containers. Before this lab launches another trial, reserve the new worker's
memory against **configured limits** of existing containers as well as checking
actual available memory. Stop and resume the sweep when capacity is unavailable.
A scored independent gate needs adequate capacity for official environments;
shrinking their resource settings to fit this host would change the experiment.

The official 2.1 repository was inspected at
`7131e4375048a0e408a8fb404b5f499d726b695b`: 89 tasks, all CPU-only, with maxima of
4 CPUs and 8 GiB RAM per task. At the lab's 3× headroom, the largest trials need
12 CPUs and 24 GiB RAM. The account currently permits 6 CPUs and 12 GiB total,
already shared by two servers, and both IPv4 slots are occupied. Full-suite
execution therefore needs an UpCloud quota increase. Do not present a small
resource-filtered subset as satisfying this full independent gate.

`lab.harbor_agent:DSHAgent` is the adapter for official Harbor, using a
credential-free export of the same pinned DSH runtime. Its setup contract has
been checked against the installed Harbor source. It has **not** completed an
official Terminal-Bench oracle or model trial yet. Runtime portability still
needs end-to-end validation on the dedicated AMD64 worker before scored runs.

The relocated ARM64 runtime passed an offline scripted tool check in a bare
Debian Bookworm container for all three arms. This is portability evidence,
not official benchmark evidence; the dedicated UpCloud worker uses AMD64 and
still needs its own validation. Harbor owns task isolation. Its DSH worker uses
the same `danger-full-access` filesystem mode for all arms, allowing official
tasks to modify their disposable environment outside the initial directory.
The regular private-suite worker is unchanged.

`python -m lab.terminal_report --input <controller-manifest.json> --output <report.md>`
produces an aggregate Markdown table and JSON evidence. It requires complete
paired outcomes for the frozen suite, matching evaluation fingerprints, spend
and token accounting, the original `standard` reference, and every numbered
independent attempt. It reports each variant against plain DSH and the final
champion against each variant. The caller must supply controller-normalized
official Harbor results. `lab.harbor_control` now prepares a complete interleaved
schedule, runs the official Harbor lifecycle and normalizes its results against
frozen trial configurations and trusted gateway traces. A local synthetic oracle
fixture passed through Harbor's real environment/verifier lifecycle. This is
infrastructure evidence, not a Terminal-Bench score.

The private gateway route passed on UpCloud from a separate Docker container.
`compose.harbor.yaml` publishes only on the Docker bridge IPv4, with the paid key
remaining gateway-only and per-run budgets unchanged. The dedicated-worker
runbook is [TERMINAL_BENCH_RUNBOOK.md](TERMINAL_BENCH_RUNBOOK.md).

`lab.promotion` requires independent Terminal-Bench evidence as well as private
development/held-out, two-model transfer, matched-budget, cost, leakage and
separate review gates. `lab.proposer` exports a whitelist of dev-only evidence
and generates policy modules from text. These are tested components; the full
automated proposal-to-promotion loop is not yet running.

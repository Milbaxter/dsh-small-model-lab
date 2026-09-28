# Work report — 2026-09-28

## Outcome and stopping state

The owner requested that this experiment stop and that the work be documented.
The benchmark controller and this experiment's OpenRouter gateway were stopped.
Verification found no remaining controller or running trial, grader or gateway
container belonging to this experiment. Active run tokens were closed; saved
results, traces, budget accounting and source code were retained. Existing
servers and unrelated applications were left running. No support request was
sent and no new schedule was created.

**There is no established capability gain, completed Terminal-Bench score or
final champion.** Setup and infrastructure tests passed, but they do not answer
whether the autonomy policy improves DSH.

Implementation: [PR #1](https://github.com/Milbaxter/dsh-small-model-lab/pull/1),
at commit [`8ce53f1`](https://github.com/Milbaxter/dsh-small-model-lab/commit/8ce53f16197dffd0ea58e3f778b24e33dfce28d0).
The implementation remains in that open PR; this report is documentation, not
a claim that the complete lab is operational.

## What was completed

| Area | Implementation and evidence | Limit |
|---|---|---|
| Hosted inference | Qwen3-8B through OpenRouter, pinned to the Alibaba route and declared sampling settings; execution on UpCloud CPU containers | Hosted weights/revision and quantization remain provider-managed |
| DSH configurations | Pinned CLI `0.1.7-rc.2` and Python SDK `0.1.5rc1`; minimal, standard and standard-plus-autonomy-policy configurations | Both standard arms share a documented adaptation for the 16k context budget |
| Live setup | All three arms completed the same public tool/file fixture on UpCloud | One setup fixture per arm; no comparative capability inference |
| Private benchmark | Separate private bank of 100 initial instances: 40 dev, 40 held-out, 20 transfer; completion, recovery, memory and context families | Difficulty is uncalibrated; generated instances share archetypes |
| Grading | Reference/start/empty/corrupt-output checks; separate isolated grading process; expected answers stay outside the process executing submitted code | Validation of graders does not establish task quality or model performance |
| Execution and accounting | Resumable sweeps, fresh trial environments, staged prompts, trusted gateway traces, persistent per-run/global budgets and host-capacity checks | Only a pilot and two calibration trials completed; the full baseline table is missing |
| Independent gate | Full-suite Terminal-Bench metadata freeze, paired comparisons, confidence intervals, repeated-selection correction, original plain-DSH reference and final-champion reporting | No official Terminal-Bench task was scored |
| Harbor integration | Frozen execution plans, official verifier-result ingestion, resource/configuration checks and private gateway routing | Local synthetic lifecycle checks passed; dedicated AMD64 worker validation remains |
| Improvement-loop components | Dev-only evidence exporter, bounded policy-text handling, leakage checks and promotion requirements | The automatic proposal-to-promotion loop is not running |

The public setup evidence is preserved in the PR's
[three-arm run record](https://github.com/Milbaxter/dsh-small-model-lab/blob/8ce53f16197dffd0ea58e3f778b24e33dfce28d0/docs/results/2026-09-28-upcloud-three-arms.json).
Its three runs reported approximately **$0.00559** in model charges. Separately,
the private benchmark ledger recorded **$0.011905452** settled across 15 requests,
with no unsettled reservations at shutdown. These are scoped accounting records,
not a complete account-wide bill or all troubleshooting costs.

Both calibration trials were unsuccessful. Two trials are far too few to
estimate baseline performance or compare configurations. They were retained,
not promoted into a benchmark result.

## What we learned

1. **OpenRouter removes the GPU requirement for inference.** CPU workers can run
   the environments and tools while the model is hosted. The account's GPU quota
   was zero; the promotional GPU route was unavailable. No GPU was provisioned.
2. **Credit balance and deployment quota are separate constraints.** The account
   still had substantial credit when work stopped. Adding money was not the
   demonstrated fix for the CPU-worker blocker.
3. **Shared-host capacity must account for reserved memory.** Apparently free RAM
   did not guarantee room for another trial when other containers had already
   reserved it. The sweep waited instead of overcommitting further. A Docker
   container disappearing between listing and inspection also exposed a race;
   the controller now treats that snapshot as unavailable capacity and retries.
4. **DSH setup details matter to a fair comparison.** The released standard preset
   required explicit selection in the headless SDK. Its default compaction
   headroom was unsuitable for the chosen small context window. The same
   adaptation was applied to both standard arms and recorded as a limitation.
5. **Portable binaries alone do not prove tool execution.** A relocated runtime
   started on bare Debian, but the standard tool sandbox needed platform support.
   Harbor's disposable environments now give every compared arm the same
   filesystem permission mode. Scripted tool execution passed for all three arms.
6. **Networking needs a real client-path check.** IPv6-only access was not usable
   from the existing management path. Docker's own-network hairpin check was
   also misleading. A separate Docker client successfully reached the gateway's
   private bridge address on UpCloud. No public gateway port was published.
7. **The independent benchmark must stay independent.** Proposals must use dev
   evidence only. Terminal-Bench tasks, solutions and per-task failures must not
   be fed back into candidate development. Every attempted comparison must be
   retained, including unsuccessful candidates.

## The UpCloud blocker

At the final check, the account allowed **6 CPUs, 12 GiB RAM and 2 public IPv4
addresses**. Its two existing servers each used 2 CPUs and 4 GiB RAM, and both
IPv4 slots were occupied. The shared execution host had insufficient unreserved
memory to continue calibration reliably.

The inspected Terminal-Bench 2.1 suite contains **89 CPU-only tasks**, with task
requirements up to **4 CPUs and 8 GiB RAM**. This repository's **3× resource
headroom rule** raises the largest worker requirement to **12 CPUs and 24 GiB**.
That multiplier is the lab's protocol, not Terminal-Bench's native minimum.

A draft therefore requested total account limits of **20 CPUs, 40 GiB RAM and
3 IPv4 addresses**: enough for a temporary 16-CPU/32-GiB worker alongside the two
existing servers. The request was not sent because contacting support awaited
the owner's permission. **The blocker was capacity/quota, not exhausted credit.**
Detailed account balances and credentials are not included in this public report.

## Verification and unfinished work

[CI passed for the implementation commit](https://github.com/Milbaxter/dsh-small-model-lab/actions/runs/36402079762),
including the main tests, pinned Harbor contract checks and a real Harbor/Docker
oracle/verifier lifecycle on a synthetic fixture. The private gateway route also
passed on UpCloud. None of these checks represents a Terminal-Bench result.

The intended independent schedule is 89 official reference-solution validations,
followed by 890 model trials: 89 tasks × five repetitions × two initial arms.
Official task timeouts are preserved, with predeclared lab request/token budgets.
Results must be labeled with those budgets; leaderboard comparability is unproven.

Before resuming the complete objective:

1. Obtain adequate UpCloud capacity and explicitly resume the experiment.
2. Validate a fresh AMD64 runtime and the full official environment path on the
   dedicated worker. The earlier Mac ARM64 export is unsuitable for deployment
   and became stale after subsequent code changes.
3. Complete calibration, then the three-configuration dev/held-out baseline table
   with five repetitions per task. Check context/compaction behavior empirically.
4. Finish and run the bounded proposer/reviewer loop, matched-budget controls,
   second-model transfer, ceiling checks and DeepSeek spot checks.
5. Complete official Terminal-Bench evaluation and report absolute success,
   percentage-point and relative changes, uncertainty, tokens and cost. Preserve
   the final comparison against original plain DSH; report no improvement if that
   is what the evidence shows.
6. Locate and reuse the existing external 12-hour Astra/OpenClaw schedule. Its
   repository documents the schedule, but its actual host/job was not located.

The full objective remains unfinished. The
[dedicated-worker runbook](https://github.com/Milbaxter/dsh-small-model-lab/blob/8ce53f16197dffd0ea58e3f778b24e33dfce28d0/docs/TERMINAL_BENCH_RUNBOOK.md)
and retained run state provide the restart point.

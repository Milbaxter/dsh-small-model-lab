# Task bank design

The task bank lives in a **separate private repo**. This document describes its design only; no tasks are published here.

## Families

| Family | What it tests | Example shape |
|---|---|---|
| **Multi-step completion** | Planning, tool coordination, finishing with verification | Fix a bug so the hidden tests pass; build a small script from a spec; extract data from messy files into a required format |
| **Recovery** | Handling tool failures without looping or giving up | Same kinds of tasks with injected faults: 429s, permission denied, malformed JSON, a missing file, a flaky command |
| **Memory** | Carrying information across sessions | Session 1 establishes a fact or preference; session 2 or 3 needs it to succeed; distractor facts included |
| **Long context** | Surviving compaction without losing critical state | Tasks long enough to force compaction, where exact IDs, paths or constraints from early on are required at the end |

Target mix for ~100 tasks: 35 completion, 25 recovery, 20 memory, 20 long context.

## Splits

| Split | Size | Who sees what |
|---|---|---|
| Dev | ~40 | Proposer sees tasks, traces, per-task results |
| Held-out | ~40 | Proposer sees aggregate score only |
| Transfer | ~20 | Different domains; also run on second model |

Each split contains all four families. Split is fixed before the first iteration.

Refresh: every ~20 iterations, retire a portion of held-out into dev and add fresh held-out tasks. Never move dev tasks into held-out.

## Difficulty calibration

Run baseline `standard` DSH with Qwen3-8B, k = 5:
- Tasks passed 5/5: too easy, drop or harden.
- Tasks passed 0/5 and also failed by the ceiling model: likely broken or out of reach, inspect the grader or drop.
- Aim for aggregate baseline pass rate of roughly 30–60%, the range where harness changes are visible.

## Grading

- Prefer **programmatic graders**: hidden tests, exact file/state checks, exit codes, structured output validation.
- Verify each grader: the reference solution passes, the starting state fails, and trivial or wrong solutions fail.
- LLM-judged grading only where unavoidable, with a fixed judge model and rubric, and flagged separately in results.
- Graders and hidden tests are never visible to the acting agent or the proposer.

## Sources for tasks
- Real tasks from own work history (best signal; stays private).
- Adapted public benchmark items for format reference only, checked for contamination risk; Qwen models have known contamination on common math benchmarks, so avoid those.
- Synthetic, generated-after-cutoff tasks (e.g. procedurally generated data files) where fresh instances are easy to make.

## Task format (per task)
```
task_id, family, split
instruction           # identical text given to every harness arm
workspace/            # starting state
faults.yaml           # optional injected failures (recovery family)
sessions/             # optional multi-session script (memory family)
grader                # hidden; returns pass/fail + details
budget                # max steps, tokens, wall-clock
```

## Initial bank implementation (2026-09-28)

A separate **private** task bank now contains 100 frozen procedural instances,
with the planned 40/40/20 split and 35/25/20/20 family mix. Its initial commit is
`7aee4dffd1ac76a8fc4f2491c4486514a5ce7791`. All 100 graders passed reference,
starting-state, empty-submission and corrupted-submission validation. A reference
solution also passed the isolated Docker grading path on UpCloud.

Code-repair tasks exercise revision reduction, interval merging, dependency
ordering, quota allocation and event processing. Recovery variants inject local
export corruption, missing paths, transient failures and stale verification data.
Memory uses separate SDK runtimes/sessions with run-owned persistence; context
uses a continuing session with staged background material. Exact instances,
reference answers and hidden cases remain private. This bank is **uncalibrated**;
validation is not evidence of an appropriate difficulty or real-world gains.

Submitted Python runs in a separate networkless grading container. Only test
inputs enter that container; expected answers stay in the host controller, which
compares returned values. A submission's own claim that it passed is ignored.
Future memory prompts are delivered over stdin only after the preceding stage
finishes. Gateway traces and scores stay outside the actor mount.

Related instances share archetypes. Report task-cluster intervals as planned and
an archetype-cluster sensitivity check. Terminal-Bench remains the independent
real-task gate; this synthetic development bank is not a substitute for it.

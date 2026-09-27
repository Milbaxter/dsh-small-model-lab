# DSH Small-Model Lab

**Cheap, honest, iterative testing of DeepSeek Harness (DSH) plugin setups, using a small Qwen model as the test subject.**

Status: **plan only**. Nothing here has been built or run yet.

## Why

Earlier work in [optimal-deepseek-harness-setup](https://github.com/Milbaxter/optimal-deepseek-harness-setup) built plugins and a 12-hour Astra improvement cycle, but explicitly had **no benchmark**: there is still no evidence the autonomy-policy plugin beats unmodified DSH. Two things blocked measurement:

1. **Ceiling.** The frontier/DeepSeek base model with the default harness already scores high, leaving little room to see harness improvements.
2. **Cost.** Every evaluation iteration on a large model was expensive.

A small local model (Qwen3-8B) fixes both. It fails often enough that harness changes become visible, and per-token cost on our own GPU is effectively zero. Weak models are also "noisy channels" (Shannon): they expose vague tool descriptions, ambiguous schemas and missing recovery logic that a frontier model silently compensates for.

**Goal:** a self-improving loop for DSH plugins that improves *general* capability (task completion, recovery, memory, context handling) at acceptable cost, not benchmark scores.

## Documents

| Doc | What it covers |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | The full plan: architecture, anti-overfitting gates, build phases, milestones |
| [docs/INFRA.md](docs/INFRA.md) | Hardware choice (UpCloud L40S), model serving, DSH provider wiring, cost budget |
| [docs/TASKS.md](docs/TASKS.md) | Task bank design: families, splits, difficulty calibration, grading |
| [docs/LOOP.md](docs/LOOP.md) | The improvement loop: proposer, mutation types, promotion gate, records |

## Builds on

- [optimal-deepseek-harness-setup](https://github.com/Milbaxter/optimal-deepseek-harness-setup): plugin format, Astra review rubric, 12-hour cycle
- [agent-intelligence-lab](https://github.com/Milbaxter/agent-intelligence-lab): Pareto metrics, statistical keep/drop rule, tiered evaluation funnel
- [harness-watch](https://github.com/Milbaxter/harness-watch): benchmarking protocol, failure taxonomy, held-out and matched-budget controls
- [harness-intelligence-improvements](https://github.com/Milbaxter/harness-intelligence-improvements): experiment record template, evidence standards

## License

MIT

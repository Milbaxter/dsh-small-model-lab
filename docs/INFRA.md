# Infrastructure

## Status update 2026-09-28: UpCloud GPU blocked for now

The UpCloud account quota is 6 CPU cores and 12 GB RAM, with no GPU allowed. The smallest L40S plan needs 8 cores and 64 GB. Credits expire 24 October 2026. A quota-increase request to support is pending.

Revised plan while waiting:
- **Model for P0–P2: hosted Qwen3-8B API** (OpenAI-compatible, pay per token). Listed at $0.117 / $0.455 per 1M input/output tokens on OpenRouter (one provider, 2026-09-28). Rough estimate: a 100-task × 5-run sweep at ~40k input / 3k output tokens per run is about 20M in + 1.5M out, so **~$3 per full sweep**. Verify tool-calling support on the chosen provider before relying on it, and pin the provider (hosted endpoints can change quantization or version silently).
- **UpCloud credits: CPU box within current quota** (≤6 cores, ≤12 GB) to run DSH, the runner and task sandboxes.
- **If the GPU quota is approved** early enough, move serving to the L40S (below) for full pinning control; rerun the baseline there, since results across providers are not comparable.

## Hardware decision (original)

- **Control machine:** existing MacBook Air (DSH, git, reading results). Not used for model serving.
- **Model server:** UpCloud **NVIDIA L40S (48GB)** in Helsinki, paid from ~€400 existing credits.

| UpCloud GPU | VRAM | Listed price | Approx. hours for €400 |
|---|---|---|---|
| L4 | 24GB | $0.68/h | ~600 |
| **L40S** | **48GB** | **$0.95/h (spot)** | **~450** |
| H100 | 80GB | $1.88/h | ~230 |

Prices from the UpCloud GPU page as of 2026-09-27; verify before provisioning.

Why L40S: Qwen3-8B at full precision with room for 16+ concurrent requests, and it also fits Qwen3-30B-A3B (quantized) for ceiling checks. L4 is workable but limits concurrency. H100 is overkill for 8B.

Fallback: RunPod RTX 4090 at ~$0.34/h if credits run out.

## Rough throughput and budget (estimates, to be replaced by measurements)

- Dev sweep (40 tasks × 5 runs): ~30–60 min.
- Full sweep (100 tasks × 5 runs): ~1–3 h.
- ~450 GPU hours ≈ 150–300 improvement iterations.
- Proposer calls are billed separately via existing frontier model access; one call per iteration.

## Cost traps
1. **Idle servers.** Check whether UpCloud bills stopped GPU servers. If yes, script create → sweep → delete, keeping model weights on cheap block storage.
2. **Spot interruption.** The runner must be resumable per run, not per sweep.

## Model serving

- vLLM, OpenAI-compatible server, with tool-calling parser enabled for Qwen3 (hermes-style parser).
- Pin: vLLM version, model revision (Hugging Face commit), dtype, max context, sampling (temperature, top_p), max output tokens.
- Qwen3 thinking mode: run **non-thinking** by default for speed; test thinking as a separate configuration variable, not mixed in.
- Keep the endpoint private (firewall to the control machine's IP or an SSH tunnel). No public unauthenticated endpoint.

## DSH wiring

DSH supports custom OpenAI-compatible providers (see upstream `docs/user/guide/providers.md`). Profile patch sketch:

```yaml
- id: llm-pi-ai
  config:
    providers:
      lab-vllm:
        apiKeyEnv: LAB_VLLM_KEY
        api: openai-completions
        baseURL: http://<gpu-host>:8000/v1
        compat:
          supportsDeveloperRole: false
          maxTokensField: max_tokens
        models:
          - id: Qwen/Qwen3-8B
```

The `compat` switches are the two the DSH docs identify as most common gateway incompatibilities; confirm against the pinned DSH version.

## Harness arms

- **`sdk-minimal`**: DSH's shipped minimal profile (one shell tool, one edit tool). Control arm: if a setup doesn't beat it, it adds cost without capability.
- **`standard`**: the default preset.
- **`standard` + plugins**: candidate configurations, installed into fresh disposable profiles (`DSH_HOME` per run), never into the owner's active DSH environment.

## Isolation
- Disposable `DSH_HOME` and workspace per run; no inherited credentials; telemetry off (as in the existing integration check).
- Task containers get uniform CPU/RAM limits at 3× the task minimum, so we measure the harness, not the sandbox.

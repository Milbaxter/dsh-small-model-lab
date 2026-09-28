# Infrastructure

## Hardware decision

- **Control machine:** existing MacBook Air (DSH, git, reading results). Not used for model serving.
- **Planned model server:** UpCloud **NVIDIA L40S (48GB)** in `fi-hel2`, Helsinki. Funding and GPU quota must be confirmed before deployment. Promotional balance alone does not establish eligibility.

As checked on 2026-09-28, the [live GPU policy](https://upcloud.com/docs/products/gpu-servers/availability/) says promotional credits cannot deploy GPU servers; on-demand access requires a payment of at least 50% of the promotional credit value. Older cached documentation described a trial spot exception that is absent from the live page. Ask support to confirm any exception. See [RUNBOOK.md](RUNBOOK.md) for the implemented preflight and deployment preparation.

| UpCloud GPU | VRAM | Listed price | Historical budget estimate (not credit eligibility) |
|---|---|---|---|
| L4 | 24GB | $0.68/h | ~600 |
| **L40S** | **48GB** | **$0.95/h (spot)** | **~450** |
| H100 | 80GB | $1.88/h | ~230 |

Historical price estimates from 2026-09-27; query account-currency pricing before provisioning. These estimates do not establish that promotional credits cover GPU usage.

Why L40S: Qwen3-8B at full precision with room for 16+ concurrent requests, and it also fits Qwen3-30B-A3B (quantized) for ceiling checks. L4 is workable but limits concurrency. H100 is overkill for 8B.

Fallback: RunPod RTX 4090 at ~$0.34/h if credits run out.

## Rough throughput and budget (estimates, to be replaced by measurements)

- Dev sweep (40 tasks × 5 runs): ~30–60 min.
- Full sweep (100 tasks × 5 runs): ~1–3 h.
- ~450 GPU hours ≈ 150–300 improvement iterations.
- Proposer calls are billed separately via existing frontier model access; one call per iteration.

## Cost traps
1. **Idle servers.** Stop the GPU VM after use; stopping Docker alone does not stop compute billing. [Spot compute is charged while powered on](https://upcloud.com/docs/products/gpu-servers/spot/); attached storage and reserved IPs continue billing while the VM is stopped.
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

The minimal profile does not contain `llm-pi-ai`; it needs an `insert` entry for that plugin, as implemented in `lab/worker.py`. The sketch above is an override for a profile that already contains the row.

The `compat` switches are the two the DSH docs identify as most common gateway incompatibilities; confirm against the pinned DSH version.

## Harness arms

- **`sdk-minimal`**: DSH's shipped minimal profile (one persistent shell tool; an editor requires an explicit additional plugin). Control arm: if a setup doesn't beat it, it adds cost without capability.
- **`standard`**: the default preset.
- **`standard` + plugins**: candidate configurations, installed into fresh disposable profiles (`DSH_HOME` per run), never into the owner's active DSH environment.

## Isolation
- Disposable `DSH_HOME` and workspace per run; no inherited credentials; telemetry off (as in the existing integration check).
- Task containers get uniform CPU/RAM limits at 3× the task minimum, so we measure the harness, not the sandbox.

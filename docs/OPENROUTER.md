# OpenRouter P0 backend

The hosted backend uses `qwen/qwen3-8b` through Alibaba. It requires no UpCloud GPU or local model weights. It runs DSH tools in Docker on the control machine. The UpCloud/vLLM configuration remains available as a future reproducibility backend.

`config/openrouter.json` pins the model ID, provider, sampling parameters, output cap and price ceilings. Hosted weights and quantization cannot be pinned to the vLLM model revision, so compare arms on this same hosted route and keep hosted results separate from self-hosted results. A fixed seed is a requested setting, not a guarantee of deterministic provider execution.

## Setup

Install Docker with Compose and Python 3.10+. From the repository root, create `.local/openrouter.key` containing the existing OpenRouter API key and `.local/openrouter.env` containing `LAB_VLLM_KEY=<a fresh random local gateway key>`. Use permissions 700 for `.local` and 600 for both files. `LAB_VLLM_KEY` is the shared worker-to-endpoint variable used by both backends; for OpenRouter it is only a local gateway token, never the paid API credential.

```sh
docker compose -f compose.openrouter.yaml --env-file .local/openrouter.env --profile smoke build
docker compose -f compose.openrouter.yaml --env-file .local/openrouter.env up -d --wait gateway
python3 -m lab.smoke --backend openrouter --timeout 180
docker compose -f compose.openrouter.yaml --env-file .local/openrouter.env down
```

Only the gateway receives the paid API key. The runner has no direct internet route, no owner home, no Docker socket, and no gateway audit volume. Gateway audit records under `.local/audit/gateway.jsonl` include actual requests and upstream SSE responses, including reported usage/cost where provided. Worker artifacts and native DSH session traces are under `runs/`. These local folders are ignored by Git and excluded from the Docker build context.

## Initial spending bounds

The gateway permits 20 upstream attempts **in total across restarts**, 65,536 incoming bytes per request, and 2,048 output tokens per request. It overrides caller-supplied routing, reasoning and sampling settings; no provider or model fallback is allowed. Failed attempts count too. At the configured price ceilings ($0.12/M input and $0.46/M output), 20 text requests each using a conservative 65,536 input tokens and the full output cap cost about $0.18. This is a conservative estimate, not a provider-side account credit limit. The first live smoke passed in 5.81 seconds, using 3 requests, 1,210 input tokens and 96 output tokens. OpenRouter reported $0.00018525 total cost and zero reasoning tokens. See [the smoke record](results/2026-09-28-openrouter-smoke.json).

This small durable cap is for P0 only. The gateway intentionally stops accepting requests when exhausted. Do not reset the audit or expand the cap as part of an unattended retry. A sweep-level budget and resumable accounting belong in P1.

On 2026-09-28, the [model endpoint catalog](https://openrouter.ai/api/v1/models/qwen/qwen3-8b/endpoints) listed Alibaba at $0.117/M input and $0.455/M output, with tools, non-thinking reasoning controls and seed support. Recheck before larger runs. [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) documents provider slugs, fallback disabling and maximum prices.

## What this establishes

A passing smoke means the real hosted model selected a DSH tool, produced the expected fixture file, and finished a recorded session. It does not establish general capability, baseline superiority, calibration, held-out performance, memory behavior, or a working improvement loop. The public smoke fixture is excluded from future benchmark scores.

## UpCloud CPU execution

The lab is installed at `/opt/dsh-small-model-lab` on the existing Northlight
UpCloud host. `deploy/upcloud.compose.yaml` limits one runner to 0.75 CPU and
384 MiB RAM, and the gateway to 0.25 CPU and 128 MiB. No host ports are published.
The initial live UpCloud fixture and both standard arms passed; records are in
`docs/results/`. Use `--modern --arm standard` or
`--modern --arm standard+autonomy-policy` with `lab.smoke` and
`--compose-override deploy/upcloud.compose.yaml`. See `PROFILES.md` for the runtime
pin and the small-context adaptation.

## Benchmark spending ledger

The benchmark gateway mode (`LAB_BENCHMARK=1`) requires a controller-registered
run token from `lab.budget.Ledger`. It rejects the shared plumbing token. Each
registration binds immutable model/routing/sampling configuration, a deadline,
a total token allowance and a request count. The controller alone mounts the
SQLite ledger; task containers receive only their own short-lived run token.

A transaction reserves conservative prompt/output cost and tokens before each
upstream request. Complete usage settles that reservation. Lost responses retain
the reservation across restarts. The initial ledger's global budget defaults to
$30; reopening it cannot raise that cap. SQLite serializes concurrent admission.
These controls are tested against a scripted HTTP upstream. The larger benchmark
controller and private task bank are still being implemented; the deployed
plumbing gateway retains its original 20-request cap until that controller is ready.

# P0 runbook

Status: local SDK integration passes against scripted responses, and a live Qwen3-8B smoke passed through [OpenRouter](OPENROUTER.md). The UpCloud GPU stack has not run. P1–P4 remain unimplemented.

## UpCloud eligibility comes first

Run the read-only account check from the repository:

```sh
python3 -m lab.upcloud
```

It reads `UPCLOUD_TOKEN` from the environment or `~/.config/upcloud-agent/credentials.env`, never executes that file, and never prints the token. Exit 2 means the account cannot meet even the GPU plan's minimum resource requirements. Exit 0 only passes those minimum checks; existing allocations, IP quota, capacity and billing eligibility still need confirmation.

Use `GPU-SPOT-8xCPU-64GB-1xL40S` in `fi-hel2`: 1 L40S, 8 cores, 64 GiB RAM, plus a 100 GiB Ubuntu 24.04 boot disk. Existing services count against account limits. Keep their allocations when requesting a quota increase.

The [current GPU eligibility policy](https://upcloud.com/docs/products/gpu-servers/availability/) says promotional credits cannot deploy GPU servers and that on-demand access requires a payment of at least 50% of promotional credits. Older indexed versions described a trial spot exception; do not rely on it. Obtain confirmation from support for this account before provisioning. No provisioner or payment action is hidden in these scripts.

## Prepare an approved GPU host

On a dedicated Ubuntu GPU server, install Docker Engine, Compose v2, a supported NVIDIA driver and NVIDIA Container Toolkit using the vendors' instructions. Verify `nvidia-smi` and Docker GPU access. Clone this repository onto that host. Restrict SSH to the control machine; no inbound model port is required. Never copy the UpCloud API token to the model host or task container.

Generate the model endpoint key on the host:

```sh
umask 077
python3 -c 'import secrets; print("LAB_VLLM_KEY=" + secrets.token_urlsafe(32))' > .env
```

`compose.yaml` pins vLLM 0.30.0 by digest and Qwen3-8B by Hugging Face revision. BF16, 16,384 context tokens and 4 concurrent sequences are conservative initial settings, not measured capacity claims. Non-thinking, temperature 0.7, top_p 0.8 and 2,048 output tokens are server defaults; inspect actual request/session records before making benchmark claims. Model weights are retained in the named Docker volume.

```sh
docker compose up -d --wait --wait-timeout 1800 vllm
docker compose --profile smoke build runner
python3 -m lab.smoke --backend vllm --timeout 180
```

The controller creates a fresh container, workspace, DSH home and session, grades a public plumbing fixture, and saves the result, notifications and native session JSONL under `runs/`. The model receives only the fixture instruction. This is a connectivity and tool-execution smoke, not a benchmark task or a promotion gate. Each invocation creates a distinct run; interrupted sweeps and resumable task banks are P1 work.

The runtime's `sdk-minimal` contains one persistent shell tool. Its custom provider must be **inserted** because the minimal profile has no `llm-pi-ai` row. The lab disables the DeepSeek adapter and log upload, and uses the published SDK/runtime pair 0.1.5rc1. The full `sdk` profile and autonomy-policy arm are not yet wired.

The task container has 2 CPUs, 4 GiB RAM, a PID limit, a read-only root filesystem, dropped capabilities, no owner home or Docker socket, and an internal network shared only with vLLM. It receives only the model endpoint key. The Python worker clears inherited environment variables before starting DSH. The controller forcibly removes the disposable container on timeout or interruption; a timeout alone would otherwise leave Docker running. Private task graders and benchmark traces need a stronger separate collector before P1; do not treat worker-writable files as tamper-proof evidence.

To access the model from the Mac, use an SSH tunnel:

```sh
ssh -N -L 8000:127.0.0.1:8000 your-gpu-host
```

Only `127.0.0.1:8000` is published on the host, and the model endpoint requires its key. The local Mac is a controller, not the executor of real model-generated shell commands.

## Finish the session

```sh
docker compose down
```

This stops containers, **not UpCloud billing**. Stop the GPU server in UpCloud after collecting results. [Spot compute is billed while powered on](https://upcloud.com/docs/products/gpu-servers/spot/); storage and reserved IPs continue billing while stopped. Delete only this lab's disposable server and disks when they are no longer wanted. Keep the user's other servers untouched. No unattended scheduler is installed.

## Local verification without a GPU

```sh
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
```

The integration test runs the actual pinned SDK/runtime against a local scripted SSE server. It checks tool execution, the resulting file, provider request compatibility and saved native traces. The scripted endpoint emits a fixed benign shell command; this test makes no model capability claim. Docker/GPU startup must still be verified on the approved host.

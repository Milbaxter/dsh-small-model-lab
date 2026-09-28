# Dedicated UpCloud worker: Terminal-Bench 2.1

Status: the controller and official-result ingestion are implemented and tested
with fixtures. The full Terminal-Bench suite is unrun. This procedure needs the
larger CPU quota requested from the account owner; do not run it on the shared
Northlight server.

Use a temporary 16-CPU, 32-GiB Linux worker with approximately 160 GiB storage.
The full frozen suite requires up to 12 CPUs and 24 GiB per task under the lab's
3× resource rule. Install Docker and Python 3.12. Clone this repository at the
reviewed commit and install `requirements.harbor.lock` into a separate virtual
environment. Keep the dataset, evaluator and lab checkouts clean.

Clone the official repositories alongside the lab:

- `https://github.com/harbor-framework/terminal-bench-2-1`, commit
  `7131e4375048a0e408a8fb404b5f499d726b695b`.
- `https://github.com/harbor-framework/harbor`, commit
  `a38eb549b5f3c33d16ccd5c51734b0defff8399e`.

Follow the OpenRouter setup for the private credential files. Never place the
paid key in a task environment. Build the runner and export the bundle on this
AMD64 worker; the ARM64 Mac portability bundle cannot be used here.

```sh
docker build -f deploy/Dockerfile.runner -t dsh-small-model-lab-openrouter-runner:latest .
python3 -m lab.package_runtime --output .local/harbor-runtime.tar.gz
python3 -m lab.terminal_gate --dataset ../terminal-bench-2-1 --version 2.1 --lock .local/terminal-lock.json
```

Find the worker's private Docker bridge gateway using `docker network inspect
bridge`. Set `LAB_HARBOR_BIND_IP` to that address (usually `172.17.0.1`), then:

```sh
docker compose --env-file .local/openrouter.env -f compose.benchmark.yaml -f compose.harbor.yaml up -d --build gateway
.venv-harbor/bin/python -m lab.harbor_control prepare \
  --lock .local/terminal-lock.json --dataset ../terminal-bench-2-1 \
  --evaluator ../harbor --bundle .local/harbor-runtime.tar.gz \
  --gateway "http://${LAB_HARBOR_BIND_IP}:18080/v1" \
  --state .local/terminal-run --output .local/terminal-manifest.json
.venv-harbor/bin/python -m lab.harbor_control run --manifest .local/terminal-manifest.json
```

Preparation freezes **89 oracle checks followed by 890 model trials**: 89 tasks,
five repetitions and two arms, alternating arm order. Official task timeouts
are preserved. Each model trial has the same predeclared 64-request and
600,000-token accounting cap. Reports label this a full official suite under
lab inference budgets; leaderboard comparability has not been established.

The existing immutable global ledger limit also applies. Exhausting it leaves
the experiment incomplete; never reset the ledger to continue spending.

The controller checks the loaded evaluator pin, source and bundle consistency,
full task coverage, host resources, private gateway binding and gateway health.
Every official oracle must pass before paid trials start. Completed result files
are reused on resume; interrupted trials and infrastructure failures require
inspection, never silent retries or removal from the denominator. An official
model timeout retains the verifier's outcome if usage is fully accounted.

After the full run, select the final champion using **all** promotion gates,
including the private suite and transfer checks. The reporting command does not
make that promotion decision. For example, if no candidate has earned promotion:

```sh
.venv-harbor/bin/python -m lab.harbor_control report \
  --manifest .local/terminal-manifest.json --champion standard \
  --output .local/terminal-results.md
```

Preserve the full audit and publish only aggregate reports. Do not pass official
tasks, oracle code, traces or per-task outcomes to the proposer. Delete the
dedicated worker and its disks after securely retaining the evidence.

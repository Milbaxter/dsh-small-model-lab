"""Run and grade a disposable container; stop it on timeout or interruption."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def grade(run_dir):
    """This public plumbing fixture is never part of the private evaluation bank."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    result = json.loads((run_dir / "workspace/smoke.json").read_text())
    return manifest["status"] == "completed" and result == {"status": "ok", "sum": 42}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--backend", choices=("vllm", "openrouter"), default="openrouter")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    runs = Path(os.environ.get("LAB_RUNS_DIR", ROOT / "runs")).resolve()
    runs.mkdir(parents=True, exist_ok=True)
    run_id = "smoke-" + uuid.uuid4().hex
    container = "dsh-lab-" + run_id
    env = {**os.environ, "LAB_RUNS_DIR": str(runs)}
    compose = ["docker", "compose"]
    if args.backend == "openrouter":
        compose += ["-f", "compose.openrouter.yaml", "--env-file", ".local/openrouter.env"]
    command = compose + ["run", "--rm", "--no-deps", "--name", container,
               "runner", "--run-dir", "/runs/" + run_id]
    if args.backend == "openrouter":
        command += ["--base-url", "http://gateway:8000/v1", "--config", "config/openrouter.json"]
    status = "error"
    try:
        subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=args.timeout)
        status = "pass" if grade(runs / run_id) else "fail"
    except subprocess.TimeoutExpired:
        status = "timeout"
    finally:
        # Killing the Compose client alone does not terminate its container.
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
        (runs / (run_id + ".controller.json")).write_text(json.dumps({"status": status}, indent=2))
    print(json.dumps({"status": status, "run_dir": str(runs / run_id)}))
    raise SystemExit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()

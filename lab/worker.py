"""One disposable SDK session. Run real model output only inside a container."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import time

import yaml
from deepseek_harness import DeepSeekHarness

ROOT = Path(__file__).resolve().parents[1]


def provider_patch(base_url, model):
    # sdk-minimal has no pi-ai row; overriding that absent ID is insufficient.
    return [
        {"id": "llm-deepseek", "disabled": True},
        {"id": "session-log-deepseek", "config": {"enabled": False}},
        {"id": "plugin-package-inventory-deepseek", "disabled": True},
        {"insert": [{"id": "llm-pi-ai", "name": "@deepseek-ai/dsh-llm-pi-ai",
            "config": {"providers": {"lab-model": {
                "apiKeyEnv": "LAB_VLLM_KEY", "api": "openai-completions",
                "baseURL": base_url,
                "compat": {"supportsDeveloperRole": False, "maxTokensField": "max_tokens"},
                "models": [{"id": model["model"], "contextWindow": model["max_model_len"],
                            "maxTokens": model["max_tokens"], "input": ["text"]}]
            }}}}]},
    ]


def run_once(run_dir, base_url, instruction, model):
    """Caller owns sandbox and wall-clock limit; never use with an untrusted host task."""
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    workspace = run_dir / "workspace"
    home = run_dir / "home"
    workspace.mkdir()
    home.mkdir()
    patch = run_dir / "provider.patch.yml"
    patch.write_text(yaml.safe_dump(provider_patch(base_url, model), sort_keys=False))
    started = time.monotonic()
    record = {"status": "running", "model": model, "profile": "sdk-minimal"}
    (run_dir / "manifest.json").write_text(json.dumps(record, indent=2))
    try:
        with (run_dir / "notifications.jsonl").open("w", buffering=1) as trace:
            def log(notification):
                trace.write(json.dumps(dataclasses.asdict(notification)) + "\n")
            with DeepSeekHarness(
                provider="lab-model", model=model["model"], max_tokens=model["max_tokens"],
                cwd=str(workspace), dsh_home=str(home), profile="sdk-minimal",
                patches=(str(patch),), initialize_timeout_seconds=90,
            ) as harness:
                result = harness.run(instruction, session_id="plumbing-smoke", on_notification=log)
        (run_dir / "result.json").write_text(json.dumps(dataclasses.asdict(result), indent=2))
        record.update(status="completed", finish_reason=result.finish_reason)
    except Exception as exc:
        record.update(status="error", error_type=type(exc).__name__)
        raise
    finally:
        record["wall_seconds"] = time.monotonic() - started
        (run_dir / "manifest.json").write_text(json.dumps(record, indent=2))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--base-url", default="http://vllm:8000/v1")
    parser.add_argument("--config", default="config/model.json")
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        parser.error("Real model runs require the disposable Docker runner; see docs/RUNBOOK.md")
    # SDK children inherit os.environ. Start from an allowlist, never a copied owner environment.
    keep = {k: os.environ[k] for k in ("PATH", "LANG", "LAB_VLLM_KEY") if k in os.environ}
    keep.update(HOME="/tmp/lab-home", OTEL_SDK_DISABLED="true", DO_NOT_TRACK="1")
    os.environ.clear()
    os.environ.update(keep)
    if not os.environ.get("LAB_VLLM_KEY"):
        parser.error("LAB_VLLM_KEY is required")
    model = json.loads((ROOT / args.config).read_text())
    record = run_once(args.run_dir, args.base_url,
        'Use the shell tool to create smoke.json in the current directory containing '
        '{"status":"ok","sum":42}. Read it back to verify, then finish.', model)
    print(json.dumps(record))


if __name__ == "__main__":
    main()

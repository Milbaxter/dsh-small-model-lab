"""Container-only staged trial worker. Future prompts arrive over stdin on demand."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import time

from deepseek_harness import DeepSeekHarness
from lab.profiles import compose
from lab.worker import provider_patch


def run(run_dir, model, arm, stages, base_url='http://gateway:8000/v1', workspace_path=None, dsh_bin=None):
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    home, workspace = root / 'home', Path(workspace_path) if workspace_path else root / 'workspace'
    home.mkdir(exist_ok=False)
    workspace.mkdir(exist_ok=True)
    binary, profile, patch, provenance = compose(arm, root, provider_patch(base_url, model), binary_override=dsh_bin)
    binary = dsh_bin or binary
    started = time.monotonic()
    manifest = {'status': 'running', 'provenance': provenance, 'model': model, 'stages': 0}
    try:
        with (root / 'notifications.jsonl').open('w', buffering=1) as trace:
            def log(notification):
                trace.write(json.dumps(dataclasses.asdict(notification)) + '\n')
            # Each memory session gets a fresh runtime with the same run-owned
            # persistence and workspace. Long-context stages retain the session id.
            previous = None
            harness = None
            try:
                for n, stage in enumerate(stages):
                    session = stage['session']
                    if session != previous:
                        if harness:
                            harness.close()
                        harness = DeepSeekHarness(provider='lab-model', model=model['model'],
                            max_tokens=model['max_tokens'], cwd=str(workspace), dsh_home=str(home),
                            profile=profile, dsh_bin=binary, patches=(patch,),
                            initialize_timeout_seconds=60)
                        harness.start()
                        previous = session
                    result = harness.run(stage['instruction'], session_id=session, on_notification=log)
                    (root / f'stage-{n}.json').write_text(json.dumps(dataclasses.asdict(result)))
                    manifest['stages'] = n + 1
                    manifest['finish_reason'] = result.finish_reason
                    print(json.dumps({'stage_complete': n, 'finish_reason': result.finish_reason}), flush=True)
            finally:
                if harness:
                    harness.close()
        manifest['status'] = 'completed'
    except Exception as exc:
        manifest.update(status='error', error_type=type(exc).__name__, error=str(exc)[-2000:])
        raise
    finally:
        manifest['wall_seconds'] = time.monotonic() - started
        (root / 'manifest.json').write_text(json.dumps(manifest, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', default='/run')
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        parser.error('The model worker must run inside Docker')
    keep = {k: os.environ[k] for k in ('PATH', 'LANG', 'LAB_VLLM_KEY') if k in os.environ}
    keep.update(HOME='/tmp/lab-home', OTEL_SDK_DISABLED='true', DO_NOT_TRACK='1')
    os.environ.clear()
    os.environ.update(keep)
    header = json.loads(sys.stdin.readline())
    def stages():
        for line in sys.stdin:
            message = json.loads(line)
            if message.get('end'):
                return
            yield message
    run(args.run_dir, header['model'], header['arm'], stages())


if __name__ == '__main__':
    main()

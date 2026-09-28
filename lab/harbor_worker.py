"""Single official-task invocation inside its Harbor environment."""
import json
import os
from pathlib import Path
import sys
from lab.trial_worker import run


def main():
    payload=json.load(sys.stdin)
    keep={k:os.environ[k] for k in ('PATH','LANG','LAB_VLLM_KEY','PYTHONHOME') if k in os.environ}
    # Harbor owns the disposable task environment. All compared arms need the
    # same access to its filesystem, including tasks outside the initial cwd.
    keep.update(HOME='/tmp/dsh-owner',OTEL_SDK_DISABLED='true',DO_NOT_TRACK='1',
                DSH_PERMISSION_MODE='danger-full-access')
    os.environ.clear();os.environ.update(keep)
    run('/tmp/dsh-trial',payload['model'],payload['arm'],
        [{'session':'official-task','instruction':payload['instruction']}],
        base_url=payload['gateway'],workspace_path=payload['workspace'],dsh_bin=payload['dsh_bin'])


if __name__=='__main__':main()

"""Real Harbor/Docker lifecycle on a public synthetic fixture, with no model calls."""
import asyncio
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('harbor') and os.environ.get('DSH_HARBOR_DOCKER_SMOKE'),
                     'Opt-in Docker lifecycle test in the pinned Harbor environment')
class HarborLifecycleTests(unittest.TestCase):
    def test_official_oracle_verifier_and_result_ingestion(self):
        from harbor.models.trial.config import TrialConfig
        from harbor.trial.trial import Trial
        from lab.harbor_control import normalize
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);task=root/'fixture'
            for name in ('environment','solution','tests'):(task/name).mkdir(parents=True)
            (task/'instruction.md').write_text('Write runtime-ok to /app/answer.txt. Infrastructure fixture only.')
            (task/'task.toml').write_text('''version = "1.0"
[agent]
timeout_sec = 60
[verifier]
timeout_sec = 60
[environment]
cpus = 1
memory_mb = 512
storage_mb = 1024
allow_internet = true
''')
            (task/'environment/Dockerfile').write_text('FROM debian:bookworm-slim@sha256:'
                '3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251\nWORKDIR /app\n')
            (task/'solution/solve.sh').write_text('#!/bin/bash\nprintf runtime-ok > /app/answer.txt\n')
            (task/'tests/test.sh').write_text('#!/bin/bash\nmkdir -p /logs/verifier\n'
                'if [ "$(cat /app/answer.txt)" = runtime-ok ]; then echo 1; else echo 0; fi > /logs/verifier/reward.txt\n')
            config=TrialConfig(task={'path':task},trial_name='local-harbor-fixture',trials_dir=root/'trials',
                agent={'name':'oracle'},environment={'type':'docker','delete':True})
            frozen=config.model_dump(mode='json')
            async def execute():return (await (await Trial.create(config)).run()).model_dump(mode='json')
            result=asyncio.run(execute())
            row=normalize(result,{'arm':'oracle','task_id':'fixture','config':frozen},{},root)
            self.assertTrue(row['oracle_passed'])
            self.assertIsNone(result['exception_info'])

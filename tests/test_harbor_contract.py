"""Optional Harbor adapter contract check, run with the separately pinned Harbor environment."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    from lab.harbor_agent import DSHAgent
except ImportError:
    DSHAgent=None


@unittest.skipIf(DSHAgent is None,'Harbor extra not installed in the minimal runner test environment')
class HarborContract(unittest.TestCase):
    def test_early_environment_failure_closes_run_token(self):
        class Environment:
            async def exec(self,*args,**kwargs):raise RuntimeError('environment unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'runtime.tar.gz';bundle.write_bytes(b'fixture')
            agent=DSHAgent(logs_dir=root/'logs',bundle=str(bundle),gateway='http://gateway:8000/v1')
            context=SimpleNamespace()
            with patch('lab.harbor_agent.Ledger') as ledger:
                ledger.digest.return_value='no-trace'
                with self.assertRaisesRegex(RuntimeError,'environment unavailable'):
                    asyncio.run(agent.run('fixture',Environment(),context))
                ledger.return_value.close.assert_called_once()
                self.assertFalse(context.metadata['accounting_complete'])

    def test_setup_uses_pinned_bundle_and_checks_native_runtime(self):
        class Result:
            return_code=0
        class Environment:
            def __init__(self):self.commands=[];self.uploads=[]
            async def exec(self,command,**kwargs):self.commands.append(command);return Result()
            async def upload_file(self,source,target):self.uploads.append((source,target))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'runtime.tar.gz';bundle.write_bytes(b'fixture')
            agent=DSHAgent(logs_dir=root/'logs',model_name='qwen/qwen3-8b',bundle=str(bundle),gateway='http://gateway:8000/v1')
            env=Environment();asyncio.run(agent.setup(env))
            self.assertEqual(env.uploads,[(bundle,'/tmp/dsh-runtime.tar.gz')])
            self.assertTrue(any('--version' in c for c in env.commands))
            self.assertTrue(any('@deepseek-ai/dsh/lib/bin.js' in c for c in env.commands))
            self.assertFalse(any('pip install' in c or 'npm install' in c for c in env.commands))

"""Official Harbor adapter for the same pinned DSH arms. No verifier customization."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import tempfile
import uuid

from harbor.agents.base import BaseAgent

from lab.budget import Ledger
from lab.metrics import trace_metrics

ROOT=Path(__file__).resolve().parents[1]


class DSHAgent(BaseAgent):
    def __init__(self,*args,arm='standard',repetition=0,bundle=None,gateway=None,
                 wall_seconds=900,max_requests=64,max_tokens=600000,**kwargs):
        super().__init__(*args,**kwargs)
        if arm not in ('sdk-minimal','standard','standard+autonomy-policy'):
            raise ValueError('Unknown registered DSH arm')
        self.arm=arm;self.repetition=int(repetition)
        self.bundle=Path(bundle or ROOT/'.local/harbor-runtime.tar.gz')
        self.gateway=gateway or os.environ.get('LAB_HARBOR_GATEWAY')
        if not self.gateway:raise ValueError('LAB_HARBOR_GATEWAY must point to the private budget gateway')
        self.wall_seconds=int(wall_seconds);self.max_requests=int(max_requests);self.max_tokens=int(max_tokens)

    @staticmethod
    def name():return 'dsh-small-model-lab'

    def version(self):return '0.1.7-rc.2'

    async def setup(self,environment):
        if not self.bundle.exists():raise ValueError('Build the pinned runtime bundle before evaluation')
        await environment.upload_file(self.bundle,'/tmp/dsh-runtime.tar.gz')
        result=await environment.exec('mkdir -p /opt/dsh-lab-runtime && tar -xzf /tmp/dsh-runtime.tar.gz -C /opt/dsh-lab-runtime',timeout_sec=180)
        if result.return_code:raise RuntimeError('Unable to extract pinned DSH runtime')
        result=await environment.exec('/opt/dsh-lab-runtime/runtime/bin/python3 --version && /opt/dsh-lab-runtime/runtime/bin/node --version',timeout_sec=20)
        if result.return_code:raise RuntimeError('Task image cannot execute pinned DSH runtime; no scored run started')
        # Fix only the CLI launch interpreter, leaving the task's shell PATH intact.
        result=await environment.exec("printf '%s\\n' '#!/bin/sh' 'exec /opt/dsh-lab-runtime/runtime/bin/node /opt/dsh-lab-runtime/lab/node_modules/@deepseek-ai/dsh/lib/bin.js \"$@\"' > /opt/dsh-lab-runtime/dsh && chmod 755 /opt/dsh-lab-runtime/dsh",timeout_sec=10)
        if result.return_code:raise RuntimeError('Cannot prepare DSH launcher')

    async def run(self,instruction,environment,context):
        ledger=Ledger(ROOT/'.local/bench-audit/budget.sqlite')
        model=json.loads((ROOT/'config/openrouter.json').read_text())
        model.update(seed=1729+self.repetition,max_request_bytes=262144)
        run_id=uuid.uuid4().hex
        token=ledger.register(run_id,max_requests=self.max_requests,max_tokens=self.max_tokens,
                              wall_seconds=self.wall_seconds+30,config=model)
        try:
            pwd=await environment.exec('pwd',timeout_sec=10)
            if pwd.return_code:raise RuntimeError('Cannot determine official task working directory')
            payload={'arm':self.arm,'model':model,'instruction':instruction,'workspace':pwd.stdout.strip(),
                     'gateway':self.gateway,'dsh_bin':'/opt/dsh-lab-runtime/dsh'}
            with tempfile.TemporaryDirectory() as temporary:
                file=Path(temporary)/'input.json';file.write_text(json.dumps(payload))
                await environment.upload_file(file,'/tmp/dsh-input.json')
            result=await environment.exec(
                '/opt/dsh-lab-runtime/runtime/bin/python3 -m lab.harbor_worker < /tmp/dsh-input.json > /tmp/dsh-worker.stdout 2> /tmp/dsh-worker.stderr',
                cwd='/opt/dsh-lab-runtime/lab', env={'LAB_VLLM_KEY':token,'PYTHONHOME':'/opt/dsh-lab-runtime/runtime',
                    'OTEL_SDK_DISABLED':'true','DO_NOT_TRACK':'1'},timeout_sec=self.wall_seconds)
            await environment.download_file('/tmp/dsh-worker.stdout',self.logs_dir/'dsh.stdout')
            await environment.download_file('/tmp/dsh-worker.stderr',self.logs_dir/'dsh.stderr')
            await environment.download_dir('/tmp/dsh-trial',self.logs_dir/'dsh-trace')
            if result.return_code:raise RuntimeError('DSH worker failed; preserve the infrastructure error')
        finally:
            ledger.close(run_id)
            trace=ROOT/'.local/bench-audit/runs'/(Ledger.digest(run_id)+'.jsonl')
            metrics=trace_metrics(trace)
            context.n_input_tokens=metrics['prompt_tokens'];context.n_output_tokens=metrics['completion_tokens']
            context.cost_usd=metrics['cost_usd']
            context.metadata={'arm':self.arm,'repetition':self.repetition,'gateway_run_id':run_id,
                'accounting_complete':metrics['requests']>0 and metrics['requests']==metrics['accounted_requests'],
                'runtime_bundle_sha256':hashlib.sha256(self.bundle.read_bytes()).hexdigest()}

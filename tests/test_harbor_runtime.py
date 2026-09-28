"""Opt-in relocated-runtime check inside a disposable Linux container; no model calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@unittest.skipUnless(os.environ.get('DSH_RUNTIME_ROOT'),'Requires the exported runtime inside Docker')
class HarborRuntimeTests(unittest.TestCase):
    def test_official_workspace_and_three_arms_execute_tools(self):
        self.assertTrue(Path('/.dockerenv').exists())
        root=Path(os.environ['DSH_RUNTIME_ROOT'])
        launcher=root/'dsh'
        launcher.write_text('#!/bin/sh\nexec '+str(root/'runtime/bin/node')+' '+
                            str(root/'lab/node_modules/@deepseek-ai/dsh/lib/bin.js')+' "$@"\n')
        launcher.chmod(0o755)
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(body)
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                if len(requests)==1:
                    delta={'role':'assistant','tool_calls':[{'index':0,'id':'fixture','type':'function',
                        'function':{'name':'bash','arguments':json.dumps({'description':'Check workspace',
                            'command':"printf 'runtime-ok' > portability.txt; cat portability.txt"})}}]}
                    finish='tool_calls'
                else:delta={'role':'assistant','content':'Done.'};finish='stop'
                chunks=[{'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                        {'choices':[{'index':0,'delta':{},'finish_reason':finish}]},
                        {'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
                for chunk in chunks:
                    chunk.update(id='fixture',object='chat.completion.chunk',created=0,model='qwen/qwen3-8b')
                    self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for arm in ('sdk-minimal','standard','standard+autonomy-policy'):
                with self.subTest(arm=arm),tempfile.TemporaryDirectory() as workspace:
                    requests.clear()
                    for path in ('/tmp/dsh-trial','/tmp/dsh-owner'):shutil.rmtree(path,ignore_errors=True)
                    payload={'arm':arm,'model':json.loads((root/'lab/config/openrouter.json').read_text()),
                        'workspace':workspace,'instruction':'Create portability.txt and verify it.',
                        'gateway':f'http://127.0.0.1:{server.server_port}/v1','dsh_bin':str(launcher)}
                    process=subprocess.run([str(root/'runtime/bin/python3'),'-m','lab.harbor_worker'],
                        cwd=root/'lab',input=json.dumps(payload),text=True,capture_output=True,timeout=90,
                        env={'PATH':'/usr/bin:/bin','PYTHONHOME':str(root/'runtime'),'LAB_VLLM_KEY':'mock-only'})
                    self.assertEqual(process.returncode,0,process.stderr[-3000:])
                    output=Path(workspace)/'portability.txt'
                    self.assertTrue(output.exists(),str(requests[-1].get('messages',[])[-1:]))
                    self.assertEqual(output.read_text(),'runtime-ok')
                    self.assertEqual(len(requests),2)
                    self.assertTrue(any(m['role']=='tool' for m in requests[1]['messages']))
        finally:
            server.shutdown();server.server_close();thread.join()

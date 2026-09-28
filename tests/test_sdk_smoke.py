"""Real pinned DSH runtime against scripted HTTP; no model or benchmark claim."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


class SDKSmoke(unittest.TestCase):
    def test_tool_execution_and_trace(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if len(requests) == 1:
                    delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_smoke",
                        "type": "function", "function": {"name": "bash", "arguments": json.dumps({
                            "command": "printf '%s' '{\"status\":\"ok\",\"sum\":42}' > smoke.json; cat smoke.json"})}}]}
                    finish = "tool_calls"
                else:
                    delta = {"role": "assistant", "content": "Created and verified smoke.json."}
                    finish = "stop"
                for chunk in [
                    {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
                    {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
                ]:
                    chunk.update(id="chatcmpl-smoke", object="chat.completion.chunk", created=0, model="Qwen/Qwen3-8B")
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                env = {"PATH": os.environ["PATH"], "HOME": str(root / "user"),
                       "PYTHONPATH": str(ROOT), "LAB_VLLM_KEY": "mock-only",
                       "OTEL_SDK_DISABLED": "true", "DO_NOT_TRACK": "1"}
                script = (
                    "import json,sys; from lab.worker import run_once,ROOT; "
                    "run_once(sys.argv[1],sys.argv[2],'Create smoke.json and verify it.',"
                    "json.loads((ROOT/'config/model.json').read_text()))"
                )
                proc = subprocess.Popen([sys.executable, "-c", script, str(root / "run"),
                    f"http://127.0.0.1:{server.server_port}/v1"], env=env,
                    start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    out, err = proc.communicate(timeout=120)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    out, err = proc.communicate()
                    self.fail("SDK timeout: " + err[-4000:])
                self.assertEqual(proc.returncode, 0, out + err[-6000:])
                self.assertEqual(json.loads((root / "run/workspace/smoke.json").read_text()),
                                 {"status": "ok", "sum": 42})
                self.assertEqual(len(requests), 2)
                self.assertEqual(requests[0]["model"], "Qwen/Qwen3-8B")
                self.assertEqual(requests[0]["max_tokens"], 2048)
                self.assertTrue(any(m["role"] == "tool" for m in requests[1]["messages"]))
                self.assertFalse(any(m["role"] == "developer" for m in requests[0]["messages"]))
                self.assertGreater((root / "run/notifications.jsonl").stat().st_size, 0)
                self.assertTrue(list((root / "run/home/sessions").rglob("*.jsonl")))
                self.assertEqual(json.loads((root / "run/manifest.json").read_text())["status"], "completed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()

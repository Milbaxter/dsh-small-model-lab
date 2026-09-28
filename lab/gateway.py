"""Bounded OpenRouter gateway: pins routing and keeps the paid key out of task tools."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from lab.budget import Ledger, BudgetExceeded

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config/openrouter.json").read_text())


def prepare(body, config=CONFIG):
    if body.get("model") != config["model"]:
        raise ValueError("Model is not the pinned lab model")
    # Only the chat fields DSH uses may reach the paid route. No fallback model,
    # plugins, server-side tools, or arbitrary user routing parameters.
    payload = {key: body[key] for key in
               ("messages", "tools", "tool_choice", "stream") if key in body}
    payload.update(model=config["model"], max_tokens=config["max_tokens"],
                   temperature=config["temperature"], top_p=config["top_p"], seed=config["seed"],
                   reasoning={"enabled": False},
                   provider={"only": [config["provider"]], "allow_fallbacks": False,
                             "require_parameters": True,
                             "max_price": config["max_price_per_million"]})
    if payload.get("stream"):
        payload["stream_options"] = {"include_usage": True}
    return payload


def create_server(*, secret_path="/run/secrets/openrouter_key", audit_dir="/audit",
                  client_key=None, benchmark=None, address=("0.0.0.0", 8000)):
    api_key = Path(secret_path).read_text().strip()
    client_key = client_key or os.environ["LAB_VLLM_KEY"]
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    benchmark = os.environ.get("LAB_BENCHMARK") == "1" if benchmark is None else benchmark
    ledger = Ledger(audit_dir / "budget.sqlite") if benchmark else None
    log_path = audit_dir / "gateway.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Count durable attempts, including errors: retries consume the same budget.
    attempts = sum(1 for line in log_path.read_text().splitlines()
                   if json.loads(line).get("kind") == "request") if log_path.exists() else 0

    def record(data):
        with log_path.open("a") as log:
            log.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), **data}) + "\n")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200 if self.path == "/health" else 404)
            self.end_headers()

        def do_POST(self):
            nonlocal attempts
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            config = CONFIG
            if ledger:
                try:
                    config = ledger.configuration(token)
                except BudgetExceeded:
                    self.send_error(401)
                    return
            if not ledger and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + client_key):
                self.send_error(401)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= config["max_request_bytes"]:
                    self.send_error(413)
                    return
                body = json.loads(self.rfile.read(length))
                payload = prepare(body, config)
            except (ValueError, TypeError, AttributeError):
                self.send_error(400)
                return
            if not ledger and attempts >= CONFIG["max_requests"]:
                self.send_error(429, "Lab request budget exhausted")
                return
            request_id = None
            run_id = None
            if ledger:
                # UTF-8 serialized bytes conservatively bound prompt tokens, including
                # schema/message framing. Unsettled requests retain their full reserve.
                prompt_ceiling = len(json.dumps(payload, ensure_ascii=False).encode())
                worst_cost = (prompt_ceiling * config['max_price_per_million']['prompt'] +
                              config['max_tokens'] * config['max_price_per_million']['completion']) / 1_000_000
                try:
                    request_id, run_id = ledger.reserve(token,
                        max_tokens=prompt_ceiling + config['max_tokens'], worst_cost_usd=worst_cost)
                except BudgetExceeded:
                    self.send_error(429, "Run or global budget exhausted")
                    return
            attempts += 1
            # Persist before sending, so a restart cannot reset spent requests.
            record({"kind": "request", "attempt": attempts, "request_id": request_id, "run_id": run_id, "payload": payload})
            request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json", "X-OpenRouter-Title": "DSH Small-Model Lab"})
            try:
                response = urllib.request.urlopen(request, timeout=90)
            except urllib.error.HTTPError as exc:
                record({"kind": "error", "attempt": attempts, "status": exc.code,
                        "detail": exc.read(8192).decode(errors="replace")})
                self.send_error(exc.code, "OpenRouter request rejected; inspect gateway audit")
                return
            except (urllib.error.URLError, TimeoutError):
                record({"kind": "error", "attempt": attempts, "status": "network"})
                self.send_error(502)
                return
            self.send_response(200)
            self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
            self.end_headers()
            usage = None
            try:
                with response:
                    for line in response:
                        decoded = line.decode(errors="replace").rstrip()
                        if decoded.startswith('data: {'):
                            try:
                                chunk = json.loads(decoded[6:])
                                if chunk.get('usage'):
                                    usage = chunk['usage']
                            except ValueError:
                                pass
                        record({"kind": "response", "attempt": attempts,
                                "line": line.decode(errors="replace").rstrip()})
                        self.wfile.write(line)
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                record({"kind": "interrupted", "attempt": attempts})
            finally:
                # Missing accounting keeps the worst-case charge; never assume free.
                if (ledger and usage and isinstance(usage.get('total_tokens'), int)
                        and isinstance(usage.get('cost'), (int, float))):
                    ledger.settle(request_id, used_tokens=usage['total_tokens'], cost_usd=usage['cost'])
                    record({'kind': 'usage', 'request_id': request_id, 'run_id': run_id, 'usage': usage})

    return HTTPServer(address, Handler)


if __name__ == "__main__":
    create_server().serve_forever()

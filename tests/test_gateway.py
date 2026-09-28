import unittest

from lab.gateway import prepare, CONFIG


class GatewayTests(unittest.TestCase):
    def test_caller_cannot_expand_routing_or_token_budget(self):
        payload = prepare({"model": "qwen/qwen3-8b", "messages": [{"role": "user", "content": "hi"}],
                           "stream": True, "max_tokens": 999999,
                           "provider": {"allow_fallbacks": True}, "models": ["other-model"],
                           "plugins": [{"id": "web"}], "reasoning": {"enabled": True}})
        self.assertEqual(payload["provider"]["only"], ["alibaba"])
        self.assertFalse(payload["provider"]["allow_fallbacks"])
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertFalse(payload["reasoning"]["enabled"])
        self.assertNotIn("models", payload)
        self.assertNotIn("plugins", payload)
        self.assertTrue(payload["stream_options"]["include_usage"])

    def test_other_models_are_rejected(self):
        with self.assertRaises(ValueError):
            prepare({"model": "expensive/unrequested-model"})


class LiveGatewayBudgetTests(unittest.TestCase):
    def test_per_run_auth_limit_accounting_and_private_upstream_key(self):
        import http.client
        import io
        from pathlib import Path
        import tempfile
        import threading
        from unittest.mock import patch
        from lab.budget import Ledger
        from lab.gateway import create_server
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'paid-key').write_text('paid-test-secret')
            server = create_server(secret_path=root / 'paid-key', audit_dir=root / 'audit',
                client_key='controller-only', benchmark=True, address=('127.0.0.1', 0))
            ledger = Ledger(root / 'audit/budget.sqlite')
            config = dict(CONFIG)
            token = ledger.register('r', max_requests=1, max_tokens=10000, wall_seconds=30, config=config)
            response = io.BytesIO(b'data: {"usage":{"total_tokens":42,"cost":0.0001}}\n\ndata: [DONE]\n\n')
            response.headers = {'Content-Type': 'text/event-stream'}
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(key):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                connection.request('POST', '/v1/chat/completions', json.dumps({'model': config['model'],
                    'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True}),
                    {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
                result = connection.getresponse()
                status, content = result.status, result.read()
                connection.close()
                return status, content
            try:
                with patch('lab.gateway.urllib.request.urlopen', return_value=response) as upstream:
                    self.assertEqual(request('controller-only')[0], 401)
                    self.assertEqual(request(token)[0], 200)
                    self.assertEqual(request(token)[0], 429)
                    self.assertEqual(upstream.call_count, 1)
                    self.assertEqual(upstream.call_args.args[0].get_header('Authorization'), 'Bearer paid-test-secret')
                with ledger.transaction() as db:
                    self.assertEqual(db.execute('SELECT tokens,reserved_tokens FROM runs').fetchone(), (42,0))
                audit = (root / 'audit/gateway.jsonl').read_text()
                self.assertNotIn('paid-test-secret', audit)
                self.assertNotIn(token, audit)
                self.assertIn('"run_id": "r"', audit)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

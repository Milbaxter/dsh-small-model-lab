import unittest

from lab.gateway import prepare


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

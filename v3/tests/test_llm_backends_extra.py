#!/usr/bin/env python3
"""
Tests for model discovery, the model-not-installed error, and the DeepSeek
backend (llm/backends.py). No network: transport seams are injected.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from llm import backends
from llm.backends import LLMError, LLMHTTPError

MSGS = [{"role": "user", "content": "hi"}]


def capturing_post(canned):
    calls = []

    def _post(url, headers, payload, timeout=120):
        calls.append({"url": url, "headers": headers, "payload": payload})
        return canned

    _post.calls = calls
    return _post


class TestModelListing(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_lists_installed_models(self):
        def fake_get(url, timeout=None):
            return {"models": [{"name": "mistral:7b-instruct"}, {"name": "llama3:latest"}]}
        names = backends.list_ollama_models(_get=fake_get)
        self.assertEqual(names, ["mistral:7b-instruct", "llama3:latest"])

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_returns_empty_when_ollama_down(self):
        def boom(url, timeout=None):
            raise OSError("connection refused")
        self.assertEqual(backends.list_ollama_models(_get=boom), [])


class TestOllamaModelNotFound(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_404_says_model_not_installed(self):
        def post_404(url, headers, payload, timeout=120):
            raise LLMHTTPError(404, '{"error":"model \'qwen2.5\' not found"}')
        with self.assertRaises(LLMError) as ctx:
            backends.complete(MSGS, backend="ollama", model="qwen2.5", _post=post_404)
        msg = str(ctx.exception).lower()
        self.assertIn("qwen2.5", msg)
        self.assertTrue("pull" in msg or "ollama list" in msg)
        # And it must NOT masquerade as a connection failure.
        self.assertNotIn("could not reach", msg)


class TestDeepSeek(unittest.TestCase):
    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "dk"}, clear=True)
    def test_request_shape_and_parse(self):
        post = capturing_post({"choices": [{"message": {"content": "hi"}}]})
        out = backends.complete(MSGS, backend="deepseek", _post=post)
        self.assertEqual(out, "hi")
        self.assertIn("deepseek.com", post.calls[0]["url"])
        self.assertIn("Bearer dk", post.calls[0]["headers"]["Authorization"])

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "ok"}, clear=True)
    def test_falls_back_to_openai_key(self):
        post = capturing_post({"choices": [{"message": {"content": "hi"}}]})
        out = backends.complete(MSGS, backend="deepseek", _post=post)
        self.assertEqual(out, "hi")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_key_raises(self):
        with self.assertRaises(LLMError):
            backends.complete(MSGS, backend="deepseek", _post=capturing_post({}))


if __name__ == "__main__":
    unittest.main()

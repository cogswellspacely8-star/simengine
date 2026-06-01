#!/usr/bin/env python3
"""
Tests for the opt-in LLM backend layer (llm/backends.py).
Pure stdlib unittest. The network call is isolated behind an injectable
transport seam (_post), so these tests never touch the network.
"""

import os
import sys
import unittest
from unittest import mock

# Make v3 package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from llm import backends


def capturing_post(canned):
    """Return a fake _post that records its call and returns `canned`."""
    calls = []

    def _post(url, headers, payload, timeout=120):
        calls.append({"url": url, "headers": headers, "payload": payload})
        return canned

    _post.calls = calls
    return _post


MSGS = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Say hi."},
]


class TestBackendSelection(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_default_backend_is_ollama(self):
        post = capturing_post({"message": {"content": "hi"}})
        backends.complete(MSGS, _post=post)
        self.assertIn("/api/chat", post.calls[0]["url"])

    @mock.patch.dict(os.environ, {"SIMENGINE_LLM_BACKEND": "openai", "OPENAI_API_KEY": "k"}, clear=True)
    def test_backend_from_env(self):
        post = capturing_post({"choices": [{"message": {"content": "hi"}}]})
        backends.complete(MSGS, _post=post)
        self.assertIn("/chat/completions", post.calls[0]["url"])

    @mock.patch.dict(os.environ, {"SIMENGINE_LLM_MODEL": "my-model"}, clear=True)
    def test_model_from_env(self):
        post = capturing_post({"message": {"content": "hi"}})
        backends.complete(MSGS, _post=post)
        self.assertEqual(post.calls[0]["payload"]["model"], "my-model")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_unknown_backend_raises(self):
        with self.assertRaises(backends.LLMError):
            backends.complete(MSGS, backend="not-a-backend", _post=capturing_post({}))


class TestOllama(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_request_shape(self):
        post = capturing_post({"message": {"content": "ok"}})
        backends.complete(MSGS, backend="ollama", _post=post)
        p = post.calls[0]["payload"]
        self.assertEqual(p["messages"], MSGS)
        self.assertFalse(p["stream"])
        self.assertIn("model", p)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_json_mode_sets_format(self):
        post = capturing_post({"message": {"content": "{}"}})
        backends.complete(MSGS, backend="ollama", json_mode=True, _post=post)
        self.assertEqual(post.calls[0]["payload"]["format"], "json")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_parses_content(self):
        post = capturing_post({"message": {"content": "hello there"}})
        out = backends.complete(MSGS, backend="ollama", _post=post)
        self.assertEqual(out, "hello there")


class TestOpenAI(unittest.TestCase):
    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True)
    def test_request_shape_and_auth(self):
        post = capturing_post({"choices": [{"message": {"content": "x"}}]})
        backends.complete(MSGS, backend="openai", _post=post)
        call = post.calls[0]
        self.assertIn("/chat/completions", call["url"])
        self.assertIn("Bearer secret", call["headers"]["Authorization"])

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True)
    def test_json_mode_sets_response_format(self):
        post = capturing_post({"choices": [{"message": {"content": "{}"}}]})
        backends.complete(MSGS, backend="openai", json_mode=True, _post=post)
        self.assertEqual(post.calls[0]["payload"]["response_format"], {"type": "json_object"})

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_key_raises(self):
        with self.assertRaises(backends.LLMError):
            backends.complete(MSGS, backend="openai", _post=capturing_post({}))

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True)
    def test_parses_content(self):
        post = capturing_post({"choices": [{"message": {"content": "answer"}}]})
        self.assertEqual(backends.complete(MSGS, backend="openai", _post=post), "answer")


class TestAnthropic(unittest.TestCase):
    @mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ak"}, clear=True)
    def test_splits_system_and_sets_headers(self):
        post = capturing_post({"content": [{"text": "hi"}]})
        backends.complete(MSGS, backend="anthropic", _post=post)
        call = post.calls[0]
        self.assertEqual(call["payload"]["system"], "You are helpful.")
        self.assertNotIn("system", [m["role"] for m in call["payload"]["messages"]])
        self.assertEqual(call["headers"]["x-api-key"], "ak")
        self.assertIn("anthropic-version", call["headers"])

    @mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ak"}, clear=True)
    def test_parses_content(self):
        post = capturing_post({"content": [{"text": "answer"}]})
        self.assertEqual(backends.complete(MSGS, backend="anthropic", _post=post), "answer")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_key_raises(self):
        with self.assertRaises(backends.LLMError):
            backends.complete(MSGS, backend="anthropic", _post=capturing_post({}))


class TestErrors(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_unreachable_backend_wraps_error(self):
        def boom(url, headers, payload, timeout=120):
            raise OSError("connection refused")
        with self.assertRaises(backends.LLMError) as ctx:
            backends.complete(MSGS, backend="ollama", _post=boom)
        self.assertIn("ollama", str(ctx.exception).lower())

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_bad_response_shape_raises_llmerror(self):
        post = capturing_post({"unexpected": "shape"})
        with self.assertRaises(backends.LLMError):
            backends.complete(MSGS, backend="ollama", _post=post)


if __name__ == "__main__":
    unittest.main()

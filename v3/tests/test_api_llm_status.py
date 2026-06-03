#!/usr/bin/env python3
"""
Tests for /api/llm/status (server.handle_llm_status). No network: tags getter injected.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server


def tags(names):
    def _get(url, timeout=None):
        return {"models": [{"name": n} for n in names]}
    return _get


class TestLlmStatus(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_ollama_lists_models_and_suggests_default(self):
        payload, status = server.handle_llm_status(_get=tags(["mistral:7b-instruct", "hermes3:8b"]))
        self.assertEqual(status, 200)
        self.assertEqual(payload["backend"], "ollama")
        self.assertIn("mistral:7b-instruct", payload["installed_models"])
        # qwen2.5 (default) not installed -> default falls back to an installed model
        self.assertIn(payload["default_model"], ["mistral:7b-instruct", "hermes3:8b"])
        self.assertIn("deepseek", payload["backends"])
        # the dropdown is driven by model_options; for ollama that's the installed list
        self.assertEqual(payload["model_options"], payload["installed_models"])

    @mock.patch.dict(os.environ, {"SIMENGINE_LLM_MODEL": "hermes3:8b"}, clear=True)
    def test_configured_model_kept_when_installed(self):
        payload, _ = server.handle_llm_status(_get=tags(["mistral:7b-instruct", "hermes3:8b"]))
        self.assertEqual(payload["default_model"], "hermes3:8b")

    @mock.patch.dict(os.environ, {"SIMENGINE_LLM_BACKEND": "deepseek"}, clear=True)
    def test_non_ollama_backend(self):
        payload, status = server.handle_llm_status(_get=tags([]))
        self.assertEqual(status, 200)
        self.assertEqual(payload["backend"], "deepseek")
        self.assertEqual(payload["default_model"], "deepseek-chat")
        self.assertEqual(payload["installed_models"], [])
        # the dropdown should offer the known DeepSeek models
        self.assertIn("deepseek-chat", payload["model_options"])
        self.assertIn("deepseek-reasoner", payload["model_options"])

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_options_list_all_backends_with_readiness(self):
        payload, _ = server.handle_llm_status(_get=tags(["mistral:7b-instruct"]))
        opts = payload["options"]
        backends_seen = {o["backend"] for o in opts}
        self.assertEqual(backends_seen, {"ollama", "openai", "deepseek", "anthropic"})
        # ollama model is ready; deepseek needs a key (none set)
        ds = next(o for o in opts if o["backend"] == "deepseek" and o["model"] == "deepseek-chat")
        self.assertFalse(ds["ready"])
        self.assertEqual(ds["needs"], "DEEPSEEK_API_KEY")
        ol = next(o for o in opts if o["backend"] == "ollama")
        self.assertTrue(ol["ready"])

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-x"}, clear=True)
    def test_deepseek_ready_when_key_present(self):
        payload, _ = server.handle_llm_status(_get=tags([]))
        ds = next(o for o in payload["options"] if o["backend"] == "deepseek" and o["model"] == "deepseek-chat")
        self.assertTrue(ds["ready"])


if __name__ == "__main__":
    unittest.main()

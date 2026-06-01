#!/usr/bin/env python3
"""
Tests for the /api/ask handler (server.handle_ask). No network: fake LLM injected.
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server
from llm.backends import LLMError

GOOD = {
    "name": "Coin Flip",
    "n_simulations": 300,
    "n_steps": 10,
    "parameters": {"heads": {"distribution": "bernoulli", "params": {"p": 0.5}}},
    "step_logic": [{"target": "payout", "expr": "1 if heads > 0.5 else -1"}],
    "accumulators": {"bankroll": "bankroll + payout"},
    "metrics": {"final_bankroll": {"expr": "bankroll", "format": "number"}},
    "initial_state": {"bankroll": 0},
}
GOOD_JSON = json.dumps(GOOD)
BAD_JSON = json.dumps({k: v for k, v in GOOD.items() if k != "metrics"})


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def __call__(self, messages, *, json_mode=False, backend=None, model=None):
        return self.outputs.pop(0)


def raising(messages, *, json_mode=False, backend=None, model=None):
    raise LLMError("ollama not reachable")


class TestApiAsk(unittest.TestCase):
    def test_valid_question_returns_answer(self):
        payload, status = server.handle_ask(
            {"question": "a coin flip game", "seed": 42},
            _complete=FakeLLM([GOOD_JSON, "Most games break even."]),
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["config"]["name"], "Coin Flip")
        self.assertEqual(payload["explanation"], "Most games break even.")

    def test_empty_question_is_400(self):
        payload, status = server.handle_ask({"question": "   "}, _complete=FakeLLM([]))
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_backend_unavailable_is_503(self):
        payload, status = server.handle_ask({"question": "coin flip"}, _complete=raising)
        self.assertEqual(status, 503)
        self.assertIn("error", payload)

    def test_unbuildable_config_is_422(self):
        payload, status = server.handle_ask(
            {"question": "bad"},
            _complete=FakeLLM([BAD_JSON, BAD_JSON, BAD_JSON, BAD_JSON]),
        )
        self.assertEqual(status, 422)
        self.assertFalse(payload["valid"])


if __name__ == "__main__":
    unittest.main()

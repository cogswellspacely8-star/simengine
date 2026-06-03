#!/usr/bin/env python3
"""
Tests for the shared ask orchestrator (llm/ask.py): compile -> run -> explain.
No network: one fake LLM serves both the compile call(s) and the explain call.
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from llm import ask

GOOD = {
    "name": "Coin Flip",
    "n_simulations": 500,
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
    """Serves queued outputs: compile draft(s) first, then the explanation."""
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def __call__(self, messages, *, json_mode=False, backend=None, model=None):
        return self.outputs.pop(0)


class TestAnswerQuestion(unittest.TestCase):
    def test_happy_path(self):
        fake = FakeLLM([GOOD_JSON, "Most games end near break-even."])
        res = ask.answer_question("a coin flip game", seed=42, clarify=False, coverage=False, _complete=fake)
        self.assertTrue(res["valid"])
        self.assertEqual(res["config"]["name"], "Coin Flip")
        self.assertIn("final_bankroll", res["results"]["stats"])
        self.assertEqual(res["explanation"], "Most games end near break-even.")
        self.assertEqual(res["attempts"], 1)

    def test_runs_real_simulation_numbers(self):
        fake = FakeLLM([GOOD_JSON, "explained"])
        res = ask.answer_question("coin flip", seed=42, clarify=False, coverage=False, _complete=fake)
        stats = res["results"]["stats"]["final_bankroll"]
        # Fair coin over 10 flips: median ~0, symmetric.
        self.assertEqual(stats["median"], 0.0)
        self.assertIn("safety", res["results"])

    def test_invalid_config_reports_without_running(self):
        fake = FakeLLM([BAD_JSON, BAD_JSON, BAD_JSON, BAD_JSON])
        res = ask.answer_question("bad", max_repairs=3, clarify=False, coverage=False, _complete=fake)
        self.assertFalse(res["valid"])
        self.assertIsNone(res["results"])
        self.assertTrue(res["errors"])

    def test_user_n_simulations_overrides(self):
        cfg = dict(GOOD)
        cfg["n_simulations"] = 999
        fake = FakeLLM([json.dumps(cfg), "explained"])
        res = ask.answer_question("coin flip", n_simulations=300, seed=1, clarify=False, coverage=False, _complete=fake)
        self.assertEqual(res["results"]["n_simulations"], 300)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Tests for the NL->config compiler and its validate/repair loop (llm/compiler.py).
Pure stdlib unittest. A fake LLM (no network) drives every case.
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from llm import compiler

# A valid, runnable config (the minimal coin-flip).
GOOD = {
    "name": "Coin Flip",
    "n_simulations": 1000,
    "n_steps": 10,
    "parameters": {"heads": {"distribution": "bernoulli", "params": {"p": 0.5}}},
    "step_logic": [{"target": "payout", "expr": "1 if heads > 0.5 else -1"}],
    "accumulators": {"bankroll": "bankroll + payout"},
    "metrics": {"final_bankroll": {"expr": "bankroll", "format": "number"}},
    "initial_state": {"bankroll": 0},
}
GOOD_JSON = json.dumps(GOOD)

# Same config but missing 'metrics' -> validation fails with a clear error.
BAD = dict(GOOD)
del BAD["metrics"]
BAD_JSON = json.dumps(BAD)

FENCED_GOOD = "Here is your config:\n```json\n" + GOOD_JSON + "\n```\nHope that helps!"
NON_JSON = "I'm not sure how to model that question."


class FakeLLM:
    """Returns canned outputs in order; records the messages it was given."""
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, messages, *, json_mode=False, backend=None, model=None):
        self.calls.append(messages)
        return self.outputs.pop(0)


class TestCompileConfig(unittest.TestCase):
    def test_valid_on_first_try(self):
        fake = FakeLLM([GOOD_JSON])
        res = compiler.compile_config("a coin flip game", _complete=fake)
        self.assertTrue(res["valid"])
        self.assertEqual(res["attempts"], 1)
        self.assertEqual(res["config"]["name"], "Coin Flip")
        self.assertEqual(res["errors"], [])

    def test_repairs_then_succeeds(self):
        fake = FakeLLM([BAD_JSON, GOOD_JSON])
        res = compiler.compile_config("a coin flip game", _complete=fake)
        self.assertTrue(res["valid"])
        self.assertEqual(res["attempts"], 2)
        # The repair turn must feed the validation errors back to the model.
        repair_turn = fake.calls[1]
        self.assertTrue(any("metrics" in m["content"].lower() for m in repair_turn))

    def test_exhausts_repairs_and_reports(self):
        fake = FakeLLM([BAD_JSON, BAD_JSON, BAD_JSON, BAD_JSON])
        res = compiler.compile_config("bad", max_repairs=3, _complete=fake)
        self.assertFalse(res["valid"])
        self.assertEqual(res["attempts"], 4)  # 1 initial + 3 repairs
        self.assertTrue(res["errors"])

    def test_extracts_json_from_fenced_prose(self):
        fake = FakeLLM([FENCED_GOOD])
        res = compiler.compile_config("a coin flip game", _complete=fake)
        self.assertTrue(res["valid"])
        self.assertEqual(res["config"]["name"], "Coin Flip")

    def test_non_json_is_treated_as_error_then_repaired(self):
        fake = FakeLLM([NON_JSON, GOOD_JSON])
        res = compiler.compile_config("a coin flip game", _complete=fake)
        self.assertTrue(res["valid"])
        self.assertEqual(res["attempts"], 2)

    def test_injects_n_simulations_when_missing(self):
        cfg = dict(GOOD)
        del cfg["n_simulations"]
        fake = FakeLLM([json.dumps(cfg)])
        res = compiler.compile_config("coin flip", n_simulations=2500, _complete=fake)
        self.assertTrue(res["valid"])
        self.assertEqual(res["config"]["n_simulations"], 2500)

    def test_system_prompt_carries_schema(self):
        fake = FakeLLM([GOOD_JSON])
        compiler.compile_config("coin flip", _complete=fake)
        system = fake.calls[0][0]["content"].lower()
        self.assertEqual(fake.calls[0][0]["role"], "system")
        self.assertIn("triangular", system)        # distributions listed
        self.assertIn("step_logic", system)         # schema fields described

    def test_question_reaches_the_model(self):
        fake = FakeLLM([GOOD_JSON])
        compiler.compile_config("should I take a $8k/mo contract", _complete=fake)
        user_msgs = " ".join(m["content"] for m in fake.calls[0] if m["role"] == "user")
        self.assertIn("$8k/mo contract", user_msgs)


if __name__ == "__main__":
    unittest.main()

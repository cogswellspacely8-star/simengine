#!/usr/bin/env python3
"""Tests for the fidelity/coverage check (llm/coverage.py) and its wiring + warning."""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from llm import coverage, ask

LOW = json.dumps({"fidelity": "low", "captured": [],
                  "missing": ["the year Poly overtakes Mono", "the market-cap ratio", "P(cap > $1T)"],
                  "note": "only final_cash was computed"})
FULL = json.dumps({"fidelity": "full", "captured": ["P(heads)"], "missing": [], "note": "covered"})

GOOD = {
    "name": "Coin Flip", "n_simulations": 300, "n_steps": 10,
    "parameters": {"heads": {"distribution": "bernoulli", "params": {"p": 0.5}}},
    "step_logic": [{"target": "payout", "expr": "1 if heads > 0.5 else -1"}],
    "accumulators": {"bankroll": "bankroll + payout"},
    "metrics": {"final_bankroll": {"expr": "bankroll", "format": "number"}},
    "initial_state": {"bankroll": 0},
}
GOOD_JSON = json.dumps(GOOD)


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def __call__(self, messages, *, json_mode=False, backend=None, model=None):
        return self.outputs.pop(0)


class TestAssessCoverage(unittest.TestCase):
    def test_low_fidelity_reports_missing(self):
        out = coverage.assess_coverage("complex question", GOOD, {"stats": {}}, _complete=FakeLLM([LOW]))
        self.assertEqual(out["fidelity"], "low")
        self.assertTrue(out["missing"])

    def test_fails_open_on_junk(self):
        out = coverage.assess_coverage("q", GOOD, {"stats": {}}, _complete=FakeLLM(["not json"]))
        self.assertEqual(out["fidelity"], "unknown")


class TestAnswerQuestionCoverage(unittest.TestCase):
    def test_low_fidelity_sets_warning(self):
        # call order: compile -> coverage -> explain
        fake = FakeLLM([GOOD_JSON, LOW, "Here is an answer."])
        res = ask.answer_question("a hugely complex multi-part question",
                                  clarify=False, coverage=True, _complete=fake)
        self.assertEqual(res["coverage"]["fidelity"], "low")
        self.assertIn("Reduced model", res["warning"])
        self.assertTrue(res["valid"])

    def test_full_fidelity_no_warning(self):
        fake = FakeLLM([GOOD_JSON, FULL, "Here is an answer."])
        res = ask.answer_question("a fair coin", clarify=False, coverage=True, _complete=fake)
        self.assertEqual(res["coverage"]["fidelity"], "full")
        self.assertEqual(res["warning"], "")


if __name__ == "__main__":
    unittest.main()

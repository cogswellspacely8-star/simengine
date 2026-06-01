#!/usr/bin/env python3
"""
Tests for the result explainer (llm/explain.py). No network: a fake LLM drives it,
and the deterministic engine narrative is the fallback when the LLM is unavailable.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from llm import explain
from llm.backends import LLMError

RESULTS = {
    "stats": {"profit": {"median": 1234, "p10": -200, "p90": 3000, "format": "dollar"}},
    "safety": {"all_passed": True, "chance": [], "cvar": []},
    "narrative": "Profit: median $1,234 (80% range: -$200 to $3,000). All safety constraints passed.",
    "n_simulations": 5000,
}


class FakeLLM:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def __call__(self, messages, *, json_mode=False, backend=None, model=None):
        self.calls.append(messages)
        return self.output


def raising(messages, *, json_mode=False, backend=None, model=None):
    raise LLMError("backend unavailable")


class TestExplain(unittest.TestCase):
    def test_returns_model_explanation(self):
        fake = FakeLLM("Bottom line: the contract looks worth taking.")
        out = explain.explain_results("Should I take it?", RESULTS, _complete=fake)
        self.assertEqual(out, "Bottom line: the contract looks worth taking.")

    def test_passes_question_and_numbers_to_model(self):
        fake = FakeLLM("ok")
        explain.explain_results("Should I take the $8k contract?", RESULTS, _complete=fake)
        joined = " ".join(m["content"] for m in fake.calls[0])
        self.assertIn("$8k contract", joined)
        self.assertIn("1234", joined)  # the real median is in the prompt

    def test_falls_back_to_narrative_on_llm_error(self):
        out = explain.explain_results("Should I take it?", RESULTS, _complete=raising)
        self.assertEqual(out, RESULTS["narrative"])

    def test_falls_back_on_empty_output(self):
        fake = FakeLLM("   ")
        out = explain.explain_results("Should I take it?", RESULTS, _complete=fake)
        self.assertEqual(out, RESULTS["narrative"])


if __name__ == "__main__":
    unittest.main()

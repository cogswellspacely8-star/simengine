#!/usr/bin/env python3
"""
Tests for the clarifying-question pre-check (llm/clarify.py) and its wiring into
answer_question. No network: a fake LLM is injected.
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from llm import clarify, ask

NOT_READY = json.dumps({"ready": False, "questions": ["Win what?", "What are the odds of one attempt?"]})
READY = json.dumps({"ready": True, "questions": []})
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
        self.calls = 0

    def __call__(self, messages, *, json_mode=False, backend=None, model=None):
        self.calls += 1
        return self.outputs.pop(0)


class TestAssess(unittest.TestCase):
    def test_not_ready_returns_questions(self):
        out = clarify.assess_question("will I win", _complete=FakeLLM([NOT_READY]))
        self.assertFalse(out["ready"])
        self.assertEqual(len(out["questions"]), 2)

    def test_ready_passes(self):
        out = clarify.assess_question("a fair coin over 10 flips", _complete=FakeLLM([READY]))
        self.assertTrue(out["ready"])

    def test_fails_open_on_junk(self):
        out = clarify.assess_question("anything", _complete=FakeLLM(["not json at all"]))
        self.assertTrue(out["ready"])  # don't block on a classifier hiccup

    def test_not_ready_without_questions_does_not_block(self):
        out = clarify.assess_question("x", _complete=FakeLLM([json.dumps({"ready": False, "questions": []})]))
        self.assertTrue(out["ready"])


class TestAnswerQuestionClarify(unittest.TestCase):
    def test_vague_question_asks_instead_of_modeling(self):
        fake = FakeLLM([NOT_READY])
        res = ask.answer_question("will I win", clarify=True, _complete=fake)
        self.assertTrue(res["needs_clarification"])
        self.assertFalse(res["valid"])
        self.assertTrue(res["questions"])
        self.assertIsNone(res["results"])
        self.assertEqual(fake.calls, 1)  # stopped before compiling

    def test_ready_question_proceeds_to_model(self):
        fake = FakeLLM([READY, GOOD_JSON, "Most games break even."])
        res = ask.answer_question("a fair coin over 10 flips", seed=42, clarify=True, _complete=fake)
        self.assertTrue(res["valid"])
        self.assertFalse(res["needs_clarification"])
        self.assertEqual(res["explanation"], "Most games break even.")


if __name__ == "__main__":
    unittest.main()

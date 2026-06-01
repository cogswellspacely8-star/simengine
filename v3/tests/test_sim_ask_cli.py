#!/usr/bin/env python3
"""
Tests for the sim_ask CLI (sim_ask.py). No network: a fake LLM is injected.
"""

import os
import sys
import io
import json
import contextlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sim_ask

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


def run_cli(argv, outputs):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = sim_ask.main(argv, _complete=FakeLLM(outputs))
    return code, out.getvalue()


class TestSimAskCLI(unittest.TestCase):
    def test_human_output(self):
        code, text = run_cli(["a coin flip game", "--seed", "42"],
                             [GOOD_JSON, "Most games end near break-even."])
        self.assertEqual(code, 0)
        self.assertIn("Most games end near break-even.", text)
        self.assertIn("Final Bankroll", text)

    def test_json_output_is_valid(self):
        code, text = run_cli(["coin flip", "--json"], [GOOD_JSON, "explained"])
        self.assertEqual(code, 0)
        payload = json.loads(text)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["config"]["name"], "Coin Flip")

    def test_invalid_returns_nonzero(self):
        code, _ = run_cli(["bad question", "--max-repairs", "1"],
                          [BAD_JSON, BAD_JSON])
        self.assertEqual(code, 1)

    def test_save_writes_domain_file(self):
        domains_dir = os.path.join(os.path.dirname(__file__), "..", "domains")
        target = os.path.join(domains_dir, "cli_smoketest.json")
        if os.path.exists(target):
            os.remove(target)
        try:
            code, _ = run_cli(["coin flip", "--save", "cli_smoketest"],
                              [GOOD_JSON, "explained"])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(target))
        finally:
            if os.path.exists(target):
                os.remove(target)


if __name__ == "__main__":
    unittest.main()

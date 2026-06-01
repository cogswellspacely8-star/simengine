#!/usr/bin/env python3
"""
Tests for the decide_under_uncertainty MCP handler (mcp_server.py).
Uses only Python stdlib unittest — zero external dependencies.
"""

import os
import sys
import unittest

# Make v3 package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import mcp_server

# Tiny inline domain whose only metric is uniform(0, 10): metric "total"
# after a single step equals the sampled value x.
DECIDE_CONFIG = {
    "name": "Decide Test",
    "n_simulations": 400,
    "n_steps": 1,
    "parameters": {
        "x": {"distribution": "uniform", "params": {"low": 0, "high": 10}}
    },
    "step_logic": [{"target": "y", "expr": "x"}],
    "accumulators": {"total": "total + y"},
    "metrics": {"total": {"expr": "total", "format": "number"}},
    "initial_state": {"total": 0},
}


def _decide(**args):
    return mcp_server.handle_decide_under_uncertainty(args)


class TestDecideUnderUncertainty(unittest.TestCase):
    def test_proceeds_when_distribution_fully_within_bounds(self):
        res = _decide(config=DECIDE_CONFIG, metric="total",
                      acceptable={"min": -100, "max": 100})
        self.assertTrue(res["proceed"])
        self.assertEqual(res["decision"], "proceed")
        self.assertAlmostEqual(res["probability_within_bounds"], 1.0)

    def test_escalates_when_distribution_fully_outside_bounds(self):
        res = _decide(config=DECIDE_CONFIG, metric="total",
                      acceptable={"min": 100, "max": 200})
        self.assertFalse(res["proceed"])
        self.assertEqual(res["decision"], "escalate")
        self.assertAlmostEqual(res["probability_within_bounds"], 0.0)

    def test_escalates_when_probability_below_confidence(self):
        # P(0 <= total <= 5) ~= 0.5 for uniform(0,10); 0.9 threshold not met.
        res = _decide(config=DECIDE_CONFIG, metric="total",
                      acceptable={"min": 0, "max": 5}, min_confidence=0.9)
        self.assertFalse(res["proceed"])
        self.assertGreater(res["probability_within_bounds"], 0.3)
        self.assertLess(res["probability_within_bounds"], 0.7)

    def test_one_sided_lower_bound_only(self):
        res = _decide(config=DECIDE_CONFIG, metric="total",
                      acceptable={"min": -1}, min_confidence=0.8)
        self.assertTrue(res["proceed"])
        self.assertAlmostEqual(res["probability_within_bounds"], 1.0)

    def test_returns_distribution_stats(self):
        res = _decide(config=DECIDE_CONFIG, metric="total",
                      acceptable={"min": 0, "max": 10})
        self.assertIn("distribution", res)
        self.assertIn("median", res["distribution"])

    def test_error_when_no_bounds_given(self):
        res = _decide(config=DECIDE_CONFIG, metric="total", acceptable={})
        self.assertIn("error", res)

    def test_error_when_metric_missing(self):
        res = _decide(config=DECIDE_CONFIG, metric="does_not_exist",
                      acceptable={"min": 0})
        self.assertIn("error", res)

    def test_error_when_no_config_or_domain(self):
        res = _decide(metric="total", acceptable={"min": 0})
        self.assertIn("error", res)

    def test_tool_is_registered(self):
        names = [t["name"] for t in mcp_server.TOOLS]
        self.assertIn("decide_under_uncertainty", names)
        self.assertIn("decide_under_uncertainty", mcp_server.HANDLERS)


if __name__ == "__main__":
    unittest.main()

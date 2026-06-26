#!/usr/bin/env python3
"""Headline summary for binary/indicator metrics.

A "100 if cond else 0" metric yields per-run values of 0 or 100; its median
collapses to its mode, so the old headline read "most likely 0.0/50.0/100.0".
The event probability is the mean. Indicator-ness is detected from the raw value
SET (percentiles interpolate off-grid and miss tail / 50-50 / high rates), so the
fix must hold across the whole 0..1 probability band — including the 5-10% tails
that are the decision-critical chance-constraint zone. Count metrics (0..N) must
NOT be reclassified.
"""
import os
import sys
import copy
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import kernel
import server


def _indicator_config(rate, scale=100):
    return {
        "name": "ind", "n_simulations": 4000, "n_steps": 1, "seed": 11,
        "parameters": {"hit": {"distribution": "bernoulli", "params": {"p": rate}}},
        "controls": {}, "exogenous": {},
        "initial_state": {},
        "step_logic": [{"target": "ind", "expr": f"hit * {scale}"}],
        "metrics": {"ind": {"expr": "ind"}},
    }


def _run(cfg):
    return kernel.run_monte_carlo(kernel.DomainConfig.from_dict(cfg), seed=11)


class TestIndicatorAnnotation(unittest.TestCase):
    def test_probability_recovered_across_the_band(self):
        # Including the tail (0.05) and high (0.90) rates the old percentile gate missed.
        for rate in (0.05, 0.10, 0.50, 0.90):
            mc = _run(_indicator_config(rate))
            bp = mc["stats"]["ind"].get("binary_prob")
            self.assertIsNotNone(bp, f"rate {rate}: indicator not detected")
            self.assertAlmostEqual(bp, rate, delta=0.03, msg=f"rate {rate} -> {bp}")

    def test_zero_one_scale_indicator(self):
        mc = _run(_indicator_config(0.3, scale=1))
        self.assertAlmostEqual(mc["stats"]["ind"]["binary_prob"], 0.3, delta=0.03)

    def test_count_metric_is_not_an_indicator(self):
        cfg = {
            "name": "cnt", "n_simulations": 4000, "n_steps": 1, "seed": 11,
            "parameters": {"a": {"distribution": "bernoulli", "params": {"p": 0.5}},
                           "b": {"distribution": "bernoulli", "params": {"p": 0.5}}},
            "controls": {}, "exogenous": {}, "initial_state": {},
            "step_logic": [{"target": "cnt", "expr": "a + b"}],
            "metrics": {"cnt": {"expr": "cnt"}},
        }
        self.assertNotIn("binary_prob", _run(cfg)["stats"]["cnt"])

    def test_continuous_metric_is_not_an_indicator(self):
        cfg = {
            "name": "cont", "n_simulations": 2000, "n_steps": 1, "seed": 11,
            "parameters": {"x": {"distribution": "normal", "params": {"mean": 10, "std": 3}}},
            "controls": {}, "exogenous": {}, "initial_state": {},
            "step_logic": [{"target": "y", "expr": "x"}],
            "metrics": {"y": {"expr": "y"}},
        }
        self.assertNotIn("binary_prob", _run(cfg)["stats"]["y"])


class TestIndicatorProbabilityHelper(unittest.TestCase):
    def test_reads_binary_prob(self):
        self.assertEqual(kernel.indicator_probability({"binary_prob": 0.324}), 0.324)

    def test_none_without_flag(self):
        self.assertIsNone(kernel.indicator_probability({"mean": 5.0, "median": 0.0}))


class TestNarrativeBinaryMetric(unittest.TestCase):
    def test_tail_indicator_reports_probability_not_zero(self):
        mc = _run(_indicator_config(0.05))
        narr = server.generate_narrative(mc["stats"], {}, {})
        self.assertNotIn("most likely 0.0", narr)
        self.assertIn("5% chance", narr)

    def test_majority_true_indicator_not_reported_as_certain(self):
        mc = _run(_indicator_config(0.90))
        narr = server.generate_narrative(mc["stats"], {}, {})
        self.assertNotIn("most likely 100.0", narr)
        self.assertIn("90% chance", narr)

    def test_continuous_metric_keeps_median_phrasing(self):
        cont = {"year_end_rate_pct": {"mean": 3.1, "median": 3.0, "std": 0.5,
                "p10": 2.2, "p25": 2.6, "p75": 3.4, "p90": 4.0, "format": "number"}}
        self.assertIn("most likely", server.generate_narrative(cont, {}, {}))


if __name__ == "__main__":
    unittest.main()

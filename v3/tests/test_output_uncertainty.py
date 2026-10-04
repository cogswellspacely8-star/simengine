#!/usr/bin/env python3
"""Monte Carlo error on the outputs: ci95 per metric, Wilson interval and
borderline flag on chance constraints (2026-10-03 review, phase 1)."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kernel


def _cfg(n=5000, **over):
    base = {
        "name": "u", "n_simulations": n, "n_steps": 1,
        "parameters": {
            "x": {"distribution": "normal", "params": {"mean": 100, "std": 10}},
            "u": {"distribution": "uniform", "params": {"low": 0, "high": 1}},
        },
        "step_logic": [{"target": "y", "expr": "x"}],
        "metrics": {
            "x_out": {"expr": "x"},
            "u_out": {"expr": "u"},
            "hit": {"expr": "100 if u < 0.3 else 0"},
        },
    }
    base.update(over)
    return kernel.DomainConfig(base)


class TestWilson(unittest.TestCase):
    def test_edges_and_center(self):
        self.assertEqual(kernel.wilson_interval(0, 0), (0.0, 0.0))
        lo, hi = kernel.wilson_interval(0, 50)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0)
        lo, hi = kernel.wilson_interval(50, 50)
        self.assertEqual(hi, 1.0)
        lo, hi = kernel.wilson_interval(300, 1000)
        self.assertLess(lo, 0.3)
        self.assertGreater(hi, 0.3)
        self.assertAlmostEqual(hi - lo, 2 * 1.96 * math.sqrt(0.3 * 0.7 / 1000), delta=0.002)


class TestQuantileInterval(unittest.TestCase):
    def test_brackets_true_quantile_of_uniform(self):
        import random
        random.seed(3)
        sv = sorted(random.random() for _ in range(5000))
        lo, hi = kernel.quantile_interval(sv, 10)
        self.assertLess(lo, 0.1)
        self.assertGreater(hi, 0.1)
        self.assertLess(hi - lo, 0.03)

    def test_single_value(self):
        self.assertEqual(kernel.quantile_interval([7.0], 50), (7.0, 7.0))
        self.assertEqual(kernel.quantile_interval([], 50), (0.0, 0.0))


class TestCi95OnStats(unittest.TestCase):
    def setUp(self):
        self.mc = kernel.run_monte_carlo(_cfg(), seed=11)

    def test_every_metric_has_ci95_and_n(self):
        for m, s in self.mc["stats"].items():
            self.assertIn("ci95", s, m)
            self.assertEqual(s["n"], 5000)
            for key in ("mean", "median", "p10", "p90"):
                lo, hi = s["ci95"][key]
                self.assertLessEqual(lo, s[key] + 1e-9, (m, key))
                self.assertGreaterEqual(hi, s[key] - 1e-9, (m, key))

    def test_mean_interval_width_matches_theory(self):
        s = self.mc["stats"]["x_out"]
        lo, hi = s["ci95"]["mean"]
        expected = 2 * 1.96 * 10 / math.sqrt(5000)
        self.assertAlmostEqual(hi - lo, expected, delta=0.05)
        self.assertLess(lo, 100)
        self.assertGreater(hi, 100)

    def test_indicator_gets_wilson_interval(self):
        s = self.mc["stats"]["hit"]
        self.assertIn("binary_prob", s)
        lo, hi = s["ci95"]["binary_prob"]
        self.assertLess(lo, 0.3)
        self.assertGreater(hi, 0.3)
        self.assertNotIn("binary_prob", self.mc["stats"]["x_out"]["ci95"])

    def test_more_runs_narrow_the_interval(self):
        small = kernel.run_monte_carlo(_cfg(n=500), seed=1)["stats"]["x_out"]["ci95"]["mean"]
        large = kernel.run_monte_carlo(_cfg(n=8000), seed=1)["stats"]["x_out"]["ci95"]["mean"]
        self.assertGreater(small[1] - small[0], 3 * (large[1] - large[0]))


class TestChanceConstraintBorderline(unittest.TestCase):
    def _safety(self, max_prob):
        mc = kernel.run_monte_carlo(_cfg(n=2000), seed=5)
        return kernel.evaluate_safety(mc, {"chance_constraints": [
            {"metric": "u_out", "condition": "below", "threshold": 0.3, "max_prob": max_prob}]})

    def test_limit_inside_interval_is_borderline(self):
        cc = self._safety(0.305)["chance"][0]
        self.assertIn("actual_prob_ci95", cc)
        self.assertTrue(cc["borderline"])
        lo, hi = cc["actual_prob_ci95"]
        self.assertLess(lo, cc["actual_prob"])
        self.assertGreater(hi, cc["actual_prob"])

    def test_limit_far_away_is_not_borderline(self):
        self.assertFalse(self._safety(0.5)["chance"][0]["borderline"])
        self.assertFalse(self._safety(0.1)["chance"][0]["borderline"])

    def test_annotation_applies_to_backend_results_too(self):
        # Shape returned by any backend (native or python) gets the same post-pass.
        raw = {"m": [0.0] * 850 + [1.0] * 150}
        res = {"chance": [{"metric": "m", "condition": "above", "threshold": 0.5,
                           "max_prob": 0.15, "actual_prob": 0.15, "passed": True}],
               "cvar": [], "all_passed": True}
        out = kernel._annotate_safety_uncertainty(res, raw)
        self.assertTrue(out["chance"][0]["borderline"])


if __name__ == "__main__":
    unittest.main()

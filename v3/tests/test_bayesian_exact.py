#!/usr/bin/env python3
"""Exact conjugate updates when the variable is already Beta / Gamma."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bayesian
from feeds import polymarket


class TestBetaExact(unittest.TestCase):
    def test_posterior_is_beta_with_added_counts(self):
        var = {"distribution": "beta", "params": {"alpha": 12, "beta": 8}}
        new, rep = bayesian.update_parameter(var, [(7, 10)])
        self.assertEqual(new, {"alpha": 19.0, "beta": 11.0})
        self.assertTrue(rep["exact"])
        self.assertAlmostEqual(rep["posterior_mean"], 19 / 30, places=4)

    def test_rescaled_beta_keeps_bounds(self):
        var = {"distribution": "beta", "params": {"alpha": 2, "beta": 2, "low": 0.1, "high": 0.9}}
        new, _ = bayesian.update_parameter(var, [(3, 3)])
        self.assertEqual((new["low"], new["high"]), (0.1, 0.9))
        self.assertEqual(new["alpha"], 5.0)

    def test_rate_observations_use_documented_pseudo_trials(self):
        var = {"distribution": "beta", "params": {"alpha": 1, "beta": 1}}
        new, rep = bayesian.update_parameter(var, [0.5])
        self.assertEqual(rep["total_trials"], 20)
        self.assertEqual(new, {"alpha": 11.0, "beta": 11.0})

    def test_update_config_round_trips_through_kernel(self):
        import kernel
        cfg = {"name": "b", "n_steps": 1, "n_simulations": 500,
               "parameters": {"p": {"distribution": "beta", "params": {"alpha": 2, "beta": 2}}},
               "step_logic": [{"target": "y", "expr": "p"}],
               "metrics": {"m": {"expr": "y"}}}
        updated, report = bayesian.update_config(cfg, {"p": [(90, 100)]})
        self.assertEqual(updated["parameters"]["p"]["params"], {"alpha": 92.0, "beta": 12.0})
        mc = kernel.run_monte_carlo(kernel.DomainConfig(updated), seed=1)
        self.assertAlmostEqual(mc["stats"]["m"]["mean"], 92 / 104, delta=0.01)


class TestGammaExact(unittest.TestCase):
    def test_rate_parametrization(self):
        var = {"distribution": "gamma", "params": {"shape": 2, "rate": 1}}
        new, rep = bayesian.update_parameter(var, [3, 5, 4])
        self.assertEqual(new, {"shape": 14.0, "rate": 4.0})
        self.assertAlmostEqual(rep["posterior_mean"], 3.5)
        self.assertTrue(rep["exact"])

    def test_scale_parametrization_matches_rate(self):
        var = {"distribution": "gamma", "params": {"shape": 2, "scale": 1.0}}
        new, rep = bayesian.update_parameter(var, [3, 5, 4])
        self.assertEqual(new["shape"], 14.0)
        self.assertAlmostEqual(new["scale"], 0.25)
        self.assertAlmostEqual(rep["posterior_mean"], 3.5)

    def test_inferred_from_distribution_not_value_range(self):
        # shape 0.5 / scale 0.5 are both in [0, 1]; the old heuristic would
        # have picked Beta-Binomial for this.
        var = {"distribution": "gamma", "params": {"shape": 0.5, "scale": 0.5}}
        _, rep = bayesian.update_parameter(var, [1, 2])
        self.assertEqual(rep["method"], "gamma_poisson")


class TestApproximatePathUnchanged(unittest.TestCase):
    def test_triangular_prior_still_moment_matched(self):
        var = {"distribution": "triangular", "params": {"low": 0.4, "mode": 0.6, "high": 0.8}}
        new, rep = bayesian.update_parameter(var, [(8, 10)], method="beta_binomial")
        self.assertNotIn("exact", rep)
        self.assertIn("mode", new)


class TestFeedBetaOutput(unittest.TestCase):
    def test_beta_prior_variable_is_exactly_updatable(self):
        var = polymarket.prior_variable(0.6, strength=20, distribution="beta")
        self.assertEqual(var["distribution"], "beta")
        self.assertEqual(var["params"], {"alpha": 12.0, "beta": 8.0})
        new, rep = bayesian.update_parameter(var, [(7, 10)])
        self.assertTrue(rep["exact"])
        self.assertEqual(new["alpha"], 19.0)

    def test_default_contract_is_still_triangular(self):
        self.assertEqual(polymarket.prior_variable(0.6)["distribution"], "triangular")
        with self.assertRaises(ValueError):
            polymarket.prior_variable(0.6, distribution="lognormal")


if __name__ == "__main__":
    unittest.main()

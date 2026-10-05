#!/usr/bin/env python3
"""Math corrections from the 2026-10-03 review ("is the math sound?" pass).

  - Beta / Gamma prior construction floored shape parameters at 1, which
    shifted the prior mean for small rates (mode 0.05 -> Beta(1, 9.5), mean
    0.095). The prior mean must equal the declared mode/mean.
  - Correlated Poisson used an inverse-CDF search capped at k < 100, biasing
    any correlated Poisson with a large rate low.
"""

import os
import random
import statistics
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bayesian
import kernel


class TestPriorMeanIsExact(unittest.TestCase):
    def test_beta_prior_mean_matches_small_mode(self):
        _, rep = bayesian.beta_binomial_update(
            {"low": 0.01, "mode": 0.05, "high": 0.1}, [(0, 0)])
        prior_mean = rep["alpha_prior"] / (rep["alpha_prior"] + rep["beta_prior"])
        self.assertAlmostEqual(prior_mean, 0.05, places=3)
        self.assertAlmostEqual(rep["alpha_prior"] + rep["beta_prior"], 10.0, places=2)

    def test_beta_prior_mean_matches_large_mode(self):
        _, rep = bayesian.beta_binomial_update(
            {"low": 0.9, "mode": 0.97, "high": 0.99}, [(0, 0)])
        prior_mean = rep["alpha_prior"] / (rep["alpha_prior"] + rep["beta_prior"])
        self.assertAlmostEqual(prior_mean, 0.97, places=3)

    def test_gamma_prior_mean_matches_small_rate(self):
        _, rep = bayesian.gamma_poisson_update({"lambda": 0.1}, [])
        self.assertAlmostEqual(rep["alpha_prior"] / rep["beta_prior"], 0.1, places=3)

    def test_posterior_still_moves_with_evidence(self):
        _, rep = bayesian.beta_binomial_update(
            {"low": 0.01, "mode": 0.05, "high": 0.1}, [(30, 100)])
        # 10 pseudo-obs at 0.05 + 100 real at 0.30 -> ~0.277
        self.assertAlmostEqual(rep["posterior_mean"], (0.5 + 30) / (10 + 100), places=3)


class TestCorrelatedPoissonLargeRate(unittest.TestCase):
    def _draws(self, lam, n=4000, seed=1):
        random.seed(seed)
        vdef = {"distribution": "poisson", "params": {"lambda": lam}}
        return [kernel.apply_correlation_to_sample(0, vdef, random.gauss(0, 1)) for _ in range(n)]

    def test_mean_tracks_rate_above_old_cap(self):
        d = self._draws(300)
        self.assertAlmostEqual(statistics.mean(d), 300, delta=3)
        self.assertGreater(max(d), 100)

    def test_variance_tracks_rate(self):
        d = self._draws(300)
        self.assertAlmostEqual(statistics.pvariance(d), 300, delta=45)

    def test_small_rate_unchanged(self):
        d = self._draws(2.5)
        self.assertAlmostEqual(statistics.mean(d), 2.5, delta=0.1)

    def test_huge_rate_uses_normal_branch(self):
        d = self._draws(5000, n=500)
        self.assertAlmostEqual(statistics.mean(d), 5000, delta=15)


if __name__ == "__main__":
    unittest.main()

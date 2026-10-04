#!/usr/bin/env python3
"""Statistical regression suite for every registered sampler.

Each distribution's seeded draws are checked against closed-form moments. This
is the class of test that would have caught the silent-zero correlated
student_t and the Poisson underflow cap: a sampler can return plausible-looking
numbers that are the wrong distribution, and only a moment check notices.

Also covers: copula correlation recovery (and the documented fact that copula
rho is not Pearson rho for skewed marginals), and — when the Rust extension is
importable — the same moment checks on the native batch sampler, so a
divergence between the two sampling paths is caught statistically even though
their RNG streams differ.
"""

import math
import os
import random
import statistics
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kernel
import native

N = 20000

# (distribution, params, expected mean, expected variance, mean tol, var tol)
CASES = [
    ("fixed", {"value": 3.5}, 3.5, 0.0, 1e-12, 1e-12),
    ("uniform", {"low": 2, "high": 5}, 3.5, 0.75, 0.02, 0.03),
    ("triangular", {"low": 0, "mode": 0.3, "high": 1}, 0.4333, 0.79 / 18, 0.006, 0.003),
    ("normal", {"mean": 10, "std": 2}, 10.0, 4.0, 0.05, 0.15),
    ("lognormal", {"median": 100, "spread": 0.5}, 100 * math.exp(0.125),
     100 ** 2 * math.exp(0.25) * (math.exp(0.25) - 1), 2.0, 400.0),
    ("bernoulli", {"p": 0.3}, 0.3, 0.21, 0.01, 0.01),
    ("poisson", {"lambda": 4}, 4.0, 4.0, 0.05, 0.2),
    ("student_t", {"df": 5, "mean": 3, "scale": 2}, 3.0, 4 * 5 / 3, 0.08, 1.2),
    ("beta", {"alpha": 2, "beta": 5}, 2 / 7, 10 / (49 * 8), 0.005, 0.002),
    ("gamma", {"shape": 3, "scale": 2}, 6.0, 12.0, 0.1, 0.8),
]


def _check(testcase, dist, draws, mean, var, mtol, vtol):
    testcase.assertAlmostEqual(statistics.mean(draws), mean, delta=mtol, msg=f"{dist} mean")
    testcase.assertAlmostEqual(statistics.pvariance(draws), var, delta=vtol, msg=f"{dist} variance")


class TestPythonSamplerMoments(unittest.TestCase):
    def test_moments_match_closed_forms(self):
        for dist, params, mean, var, mtol, vtol in CASES:
            with self.subTest(dist=dist):
                random.seed(101)
                draws = [kernel.SAMPLERS[dist](params) for _ in range(N)]
                _check(self, dist, draws, mean, var, mtol, vtol)

    def test_lognormal_median_is_the_median_param(self):
        random.seed(5)
        draws = sorted(kernel.SAMPLERS["lognormal"]({"median": 100, "spread": 0.5}) for _ in range(N))
        self.assertAlmostEqual(draws[N // 2], 100, delta=2.0)

    def test_clamps_apply(self):
        random.seed(5)
        draws = [kernel.SAMPLERS["normal"]({"mean": 0, "std": 1, "min": -1, "max": 1}) for _ in range(5000)]
        self.assertGreaterEqual(min(draws), -1)
        self.assertLessEqual(max(draws), 1)


class TestCopulaMoments(unittest.TestCase):
    def _pair(self, a_def, b_def, rho, n=6000):
        cfg = kernel.DomainConfig({
            "name": "c", "n_simulations": n, "n_steps": 1,
            "parameters": {"a": a_def, "b": b_def},
            "correlations": [{"vars": ["a", "b"], "rho": rho}],
            "step_logic": [{"target": "y", "expr": "a"}],
            "metrics": {"a": {"expr": "a"}, "b": {"expr": "b"}},
        })
        mc = kernel.run_monte_carlo(cfg, seed=9)
        return mc["raw_metrics"]["a"], mc["raw_metrics"]["b"]

    @staticmethod
    def _corr(a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)
        return cov / (statistics.pstdev(a) * statistics.pstdev(b))

    def test_normal_pair_recovers_rho_and_marginals(self):
        a, b = self._pair({"distribution": "normal", "params": {"mean": 10, "std": 2}},
                          {"distribution": "normal", "params": {"mean": -5, "std": 1}}, 0.6)
        self.assertAlmostEqual(self._corr(a, b), 0.6, delta=0.04)
        self.assertAlmostEqual(statistics.mean(a), 10, delta=0.1)
        self.assertAlmostEqual(statistics.pvariance(a), 4, delta=0.3)
        self.assertAlmostEqual(statistics.mean(b), -5, delta=0.05)

    def test_negative_rho(self):
        a, b = self._pair({"distribution": "normal", "params": {"mean": 0, "std": 1}},
                          {"distribution": "uniform", "params": {"low": 0, "high": 1}}, -0.7)
        self.assertLess(self._corr(a, b), -0.6)

    def test_skewed_marginals_realize_less_than_copula_rho(self):
        # Documented behavior: rho is the normal-score correlation; the Pearson
        # correlation of lognormal samples is attenuated.
        a, b = self._pair({"distribution": "lognormal", "params": {"median": 1, "spread": 1.0}},
                          {"distribution": "lognormal", "params": {"median": 1, "spread": 1.0}}, 0.8)
        c = self._corr(a, b)
        self.assertGreater(c, 0.35)
        self.assertLess(c, 0.8)

    def test_marginals_survive_correlation(self):
        for dist, params, mean, var, mtol, vtol in CASES:
            if dist in ("fixed",):
                continue
            with self.subTest(dist=dist):
                a, _ = self._pair({"distribution": dist, "params": params},
                                  {"distribution": "normal", "params": {"mean": 0, "std": 1}}, 0.5,
                                  n=12000)
                _check(self, dist, a, mean, var, mtol * 2.5, vtol * 2.5)


@unittest.skipUnless(native.native_available(), "native extension not built")
class TestNativeSamplerMoments(unittest.TestCase):
    """Same closed-form checks against the Rust batch sampler. The RNG streams
    differ from Python's, so this is the only parity check that is possible —
    and it is the one that matters."""

    def test_native_grid_moments(self):
        for dist, params, mean, var, mtol, vtol in CASES:
            if dist not in kernel.NATIVE_BATCH_SAMPLER_DISTRIBUTIONS:
                continue
            with self.subTest(dist=dist):
                cfg = kernel.DomainConfig({
                    "name": "n", "n_simulations": N, "n_steps": 1,
                    "parameters": {"v": {"distribution": dist, "params": params}},
                    "step_logic": [{"target": "y", "expr": "v"}],
                    "metrics": {"m": {"expr": "y"}},
                })
                runs = kernel._prepare_native_presampled_runs(cfg, N, seed=77)
                self.assertIsNotNone(runs, f"native sampler declined {dist}")
                draws = [r["v"][0] for r in runs]
                _check(self, dist, draws, mean, var, mtol, vtol)

    def test_native_binomial_fast_path(self):
        backend = native.get_native_backend()
        if not hasattr(backend, "sample_binomial"):
            self.skipTest("no native binomial")
        draws = [backend.sample_binomial(50, 0.2, 1000 + i) for i in range(N)]
        self.assertAlmostEqual(statistics.mean(draws), 10.0, delta=0.08)
        self.assertAlmostEqual(statistics.pvariance(draws), 8.0, delta=0.4)


if __name__ == "__main__":
    unittest.main()

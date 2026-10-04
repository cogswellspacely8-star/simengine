#!/usr/bin/env python3
"""First-class stochastic processes: random_walk, gbm, ar1, mean_reverting."""

import json
import math
import os
import statistics
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kernel
import diagnostics
import validation

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

DOMAIN = os.path.join(os.path.dirname(__file__), "..", "domains", "asset_price_paths.json")


def _run(vdef, n_steps, metric_expr="v", n=4000, seed=3, extra=None):
    cfg = {"name": "p", "n_simulations": n, "n_steps": n_steps,
           "parameters": {"v": vdef},
           "step_logic": [{"target": "y", "expr": "v"}],
           "metrics": {"m": {"expr": metric_expr}}}
    if extra:
        cfg.update(extra)
    mc = kernel.run_monte_carlo(kernel.DomainConfig(cfg), seed=seed)
    return mc["raw_metrics"]["m"]


class TestRecursions(unittest.TestCase):
    def test_random_walk_mean_and_variance_grow_linearly(self):
        d = _run({"distribution": "random_walk", "params": {"start": 0, "drift": 0.5, "std": 2}}, 20)
        self.assertAlmostEqual(statistics.mean(d), 10.0, delta=0.5)
        self.assertAlmostEqual(statistics.pvariance(d), 80.0, delta=8.0)

    def test_random_walk_clamp(self):
        d = _run({"distribution": "random_walk", "params": {"start": 1, "std": 3, "min": 0}}, 10)
        self.assertGreaterEqual(min(d), 0)

    def test_gbm_log_returns_are_normal_with_linear_moments(self):
        d = _run({"distribution": "gbm", "params": {"start": 100, "mu": 0.01, "sigma": 0.05}}, 25,
                 metric_expr="log(v / 100)")
        self.assertAlmostEqual(statistics.mean(d), 0.25, delta=0.015)
        self.assertAlmostEqual(statistics.pvariance(d), 0.0625, delta=0.006)

    def test_gbm_stays_positive(self):
        d = _run({"distribution": "gbm", "params": {"start": 1, "sigma": 0.5}}, 30)
        self.assertGreater(min(d), 0)

    def test_ar1_reaches_stationary_variance(self):
        d = _run({"distribution": "ar1", "params": {"mean": 10, "phi": 0.8, "std": 1}}, 60)
        self.assertAlmostEqual(statistics.mean(d), 10.0, delta=0.1)
        self.assertAlmostEqual(statistics.pvariance(d), 1 / (1 - 0.64), delta=0.3)

    def test_ar1_start_decays_toward_mean(self):
        d = _run({"distribution": "ar1", "params": {"mean": 0, "phi": 0.5, "std": 0.01, "start": 64}}, 3)
        self.assertAlmostEqual(statistics.mean(d), 8.0, delta=0.05)

    def test_mean_reverting_equals_ar1_with_phi_one_minus_theta(self):
        a = _run({"distribution": "ar1", "params": {"mean": 5, "phi": 0.8, "std": 1, "start": 9}}, 12, seed=8)
        b = _run({"distribution": "mean_reverting", "params": {"mean": 5, "theta": 0.2, "std": 1, "start": 9}}, 12, seed=8)
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=9)


class TestIntegration(unittest.TestCase):
    def test_correlated_innovations_between_two_gbms(self):
        cfg = kernel.DomainConfig({
            "name": "c", "n_simulations": 4000, "n_steps": 1,
            "exogenous": {"a": {"distribution": "gbm", "params": {"start": 100, "sigma": 0.1}},
                          "b": {"distribution": "gbm", "params": {"start": 50, "sigma": 0.2}}},
            "correlations": [{"vars": ["a", "b"], "rho": 0.8}],
            "step_logic": [{"target": "ra", "expr": "log(a / 100)"}, {"target": "rb", "expr": "log(b / 50)"}],
            "metrics": {"ra": {"expr": "ra"}, "rb": {"expr": "rb"}},
        })
        mc = kernel.run_monte_carlo(cfg, seed=4)
        ra, rb = mc["raw_metrics"]["ra"], mc["raw_metrics"]["rb"]
        ma, mb = statistics.mean(ra), statistics.mean(rb)
        cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / len(ra)
        corr = cov / (statistics.pstdev(ra) * statistics.pstdev(rb))
        self.assertAlmostEqual(corr, 0.8, delta=0.04)
        self.assertAlmostEqual(statistics.pstdev(ra), 0.1, delta=0.005)

    def test_late_binding_param(self):
        d = _run({"distribution": "gbm", "params": {"start": 100, "sigma": "$vol"}}, 1,
                 metric_expr="log(v / 100)",
                 extra={"initial_state": {"vol": 0.2}})
        self.assertAlmostEqual(statistics.pstdev(d), 0.2, delta=0.01)

    def test_inline_step_logic_process_keeps_memory(self):
        cfg = kernel.DomainConfig({
            "name": "s", "n_simulations": 4000, "n_steps": 16,
            "parameters": {"dummy": {"distribution": "fixed", "params": {"value": 0}}},
            "step_logic": [{"target": "p", "sample": {"distribution": "random_walk",
                                                      "params": {"start": 0, "std": 1}}}],
            "metrics": {"m": {"expr": "p"}},
        })
        d = kernel.run_monte_carlo(cfg, seed=2)["raw_metrics"]["m"]
        self.assertAlmostEqual(statistics.pvariance(d), 16.0, delta=1.6)

    def test_native_batch_sampler_declines_processes(self):
        cfg = kernel.DomainConfig({
            "name": "n", "n_simulations": 10, "n_steps": 2,
            "parameters": {"v": {"distribution": "gbm", "params": {"start": 1, "sigma": 0.1}}},
            "step_logic": [{"target": "y", "expr": "v"}], "metrics": {"m": {"expr": "y"}},
        })
        self.assertIsNone(kernel._build_native_variable_plan(cfg))

    def test_deterministic_baseline_is_the_zero_noise_path(self):
        cfg = kernel.DomainConfig({
            "name": "b", "n_simulations": 10, "n_steps": 10,
            "parameters": {"g": {"distribution": "gbm", "params": {"start": 100, "mu": 0.01, "sigma": 0.3}},
                           "r": {"distribution": "ar1", "params": {"mean": 10, "phi": 0.5, "std": 5, "start": 20}}},
            "step_logic": [{"target": "y", "expr": "g"}],
            "metrics": {"g_out": {"expr": "g"}, "r_out": {"expr": "r"}},
        })
        base = diagnostics.deterministic_baseline(cfg)["final_metrics"]
        self.assertAlmostEqual(base["g_out"], 100 * math.exp(0.1), places=6)
        self.assertAlmostEqual(base["r_out"], 10 + 10 * 0.5 ** 10, places=6)


class TestValidationAndSchema(unittest.TestCase):
    def _cfg(self, vdef):
        return {"name": "v", "n_steps": 3, "n_simulations": 20,
                "parameters": {"a": vdef},
                "step_logic": [{"target": "y", "expr": "a"}],
                "metrics": {"m": {"expr": "y"}}}

    def test_valid_processes_pass(self):
        for vdef in (
            {"distribution": "random_walk", "params": {"start": 0, "std": 1}},
            {"distribution": "gbm", "params": {"start": 100, "sigma": 0.02, "mu": 0.001}},
            {"distribution": "ar1", "params": {"mean": 1, "phi": 0.9, "std": 0.1}},
            {"distribution": "mean_reverting", "params": {"mean": 1, "theta": 0.3, "std": 0.1}},
        ):
            with self.subTest(dist=vdef["distribution"]):
                self.assertEqual(validation.validate_config(self._cfg(vdef)), [])

    def test_bad_params_named(self):
        cases = [
            ({"distribution": "random_walk", "params": {"start": 0}}, "missing required param 'std'"),
            ({"distribution": "gbm", "params": {"start": -5, "sigma": 0.1}}, "'start' must be positive"),
            ({"distribution": "ar1", "params": {"mean": 0, "phi": 1.5, "std": 1}}, "explosive"),
            ({"distribution": "mean_reverting", "params": {"mean": 0, "theta": 1.5, "std": 1}}, "'theta' must be in [0, 1]"),
            ({"distribution": "random_walk", "params": {"start": 0, "std": -1}}, "must be >= 0"),
        ]
        for vdef, needle in cases:
            with self.subTest(needle=needle):
                errs = validation.validate_config(self._cfg(vdef))
                self.assertTrue(any(needle in e for e in errs), errs)

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_schema_accepts_processes_and_rejects_missing_required(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "schema", "domain.schema.json")) as f:
            v = jsonschema.Draft7Validator(json.load(f))
        good = [
            {"distribution": "random_walk", "params": {"start": 0, "std": 1}},
            {"distribution": "gbm", "params": {"start": 100, "sigma": 0.02}},
            {"distribution": "ar1", "params": {"mean": 1, "phi": 0.9, "std": 0.1}},
            {"distribution": "mean_reverting", "params": {"mean": 1, "theta": 0.3, "std": 0.1}},
        ]
        for vdef in good:
            self.assertEqual(list(v.iter_errors(self._cfg(vdef))), [], vdef)
        bad = [
            {"distribution": "gbm", "params": {"start": 100}},
            {"distribution": "ar1", "params": {"mean": 1, "std": 0.1}},
        ]
        for vdef in bad:
            self.assertTrue(list(v.iter_errors(self._cfg(vdef))), vdef)


class TestExampleDomain(unittest.TestCase):
    def test_domain_validates_and_runs(self):
        with open(DOMAIN) as f:
            data = json.load(f)
        self.assertEqual(validation.validate_config(data), [])
        mc = kernel.run_monte_carlo(kernel.DomainConfig(data), seed=42, n_override=1500)
        dd = mc["raw_metrics"]["max_drawdown"]
        self.assertGreaterEqual(min(dd), 0.0)
        self.assertLessEqual(max(dd), 1.0)
        self.assertGreater(statistics.mean(dd), 0.02)
        self.assertIn("binary_prob", mc["stats"]["pct_chance_of_loss"])
        self.assertIn("ci95", mc["stats"]["final_portfolio"])
        safety = kernel.evaluate_safety(mc, data["safety"])
        self.assertIn("actual_prob_ci95", safety["chance"][0])


if __name__ == "__main__":
    unittest.main()

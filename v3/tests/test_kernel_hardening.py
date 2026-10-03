#!/usr/bin/env python3
"""Regression tests for the 2026-10-03 codebase review fixes.

Each test pins a defect that was verified by probe against the pre-fix kernel
(see docs/reviews/2026-10-03-codebase-review.md):

  1. expression allow-list enforced by the kernel itself, not only validate_config
  2. correlated student_t variables sampled as constant 0
  3. safety penalty REWARDED negative fitness (multiplicative shrink toward 0)
  4. feeds.polymarket `strength` ignored by bayesian.update_parameter
  5. metric stats rounded to 2 dp, erasing 0..1-scale metrics
  6. poisson sampler capped near 720 for any lambda above ~745
  7. seed reproducibility broke under concurrent runs (global RNG, threaded server)
  8. evolve() scored candidates on different draws; now CRN per generation + seeded
  9. version strings drifted (kernel manifest / MCP serverInfo stuck at 3.0.0)
"""

import copy
import os
import statistics
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kernel
import bayesian
from feeds import polymarket


def _cfg(**over):
    base = {
        "name": "hardening", "n_simulations": 300, "n_steps": 1,
        "parameters": {"x": {"distribution": "normal", "params": {"mean": 10, "std": 1}}},
        "step_logic": [{"target": "y", "expr": "x * 2"}],
        "metrics": {"y_out": {"expr": "y"}},
    }
    base.update(over)
    return base


class TestExpressionAllowList(unittest.TestCase):
    def test_attribute_access_rejected_at_config_load(self):
        bad = _cfg(step_logic=[{"target": "y", "expr": "x.__class__"}])
        with self.assertRaises(ValueError) as ctx:
            kernel.DomainConfig.from_dict(bad)
        self.assertIn("Attribute", str(ctx.exception))

    def test_subscript_and_comprehension_rejected(self):
        for expr in ("x[0]", "[i for i in range(3)]", "(lambda: 1)()", "f'{x}'"):
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    kernel.DomainConfig.from_dict(_cfg(metrics={"m": {"expr": expr}}))

    def test_fitness_components_are_checked_too(self):
        bad = _cfg(fitness={"components": [{"expr": "y_out_mean.__class__"}]})
        with self.assertRaises(ValueError):
            kernel.DomainConfig.from_dict(bad)

    def test_eval_expr_refuses_forbidden_syntax_even_without_config(self):
        kernel.clear_eval_expr_cache()
        self.assertEqual(kernel.eval_expr("x.__class__", {"x": 1.0}), 0)
        self.assertEqual(kernel.eval_expr("__import__('os')", {}), 0)
        self.assertEqual(kernel.eval_expr("x * 2", {"x": 1.5}), 3.0)

    def test_dunder_names_rejected(self):
        self.assertIsNotNone(kernel.expression_violation("__builtins__"))
        self.assertIsNone(kernel.expression_violation("max(x, 0) if x > 1 else 0"))

    def test_all_shipped_domains_still_load(self):
        import json, glob
        domain_dir = os.path.join(os.path.dirname(__file__), "..", "domains")
        for path in glob.glob(os.path.join(domain_dir, "*.json")):
            with self.subTest(domain=os.path.basename(path)):
                with open(path) as f:
                    kernel.DomainConfig.from_dict(json.load(f))

    def test_expr_cache_is_bounded(self):
        kernel.clear_eval_expr_cache()
        limit = kernel._COMPILED_EXPR_CACHE_MAX
        for i in range(limit + 5):
            kernel.eval_expr(f"x + {i}", {"x": 0})
        self.assertLessEqual(len(kernel._COMPILED_EXPR_CACHE), limit)


class TestCorrelatedStudentT(unittest.TestCase):
    def test_correlated_student_t_is_not_zero(self):
        cfg = kernel.DomainConfig(_cfg(
            n_simulations=400,
            parameters={
                "a": {"distribution": "student_t", "params": {"mean": 10, "scale": 1, "df": 5}},
                "b": {"distribution": "normal", "params": {"mean": 0, "std": 1}},
            },
            correlations=[{"vars": ["a", "b"], "rho": 0.8}],
            step_logic=[{"target": "y", "expr": "a"}],
            metrics={"a_out": {"expr": "a"}, "b_out": {"expr": "b"}},
        ))
        mc = kernel.run_monte_carlo(cfg, seed=3)
        self.assertGreater(mc["stats"]["a_out"]["mean"], 8.0)
        self.assertLess(mc["stats"]["a_out"]["mean"], 12.0)
        # dependence structure preserved: a and b move together
        a, b = mc["raw_metrics"]["a_out"], mc["raw_metrics"]["b_out"]
        ma, mb = statistics.mean(a), statistics.mean(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)
        corr = cov / (statistics.pstdev(a) * statistics.pstdev(b))
        self.assertGreater(corr, 0.4)


class TestFitnessPenaltySign(unittest.TestCase):
    def _fit(self, median, with_safety):
        mc = {"stats": {"cash": {"median": median}}, "raw_metrics": {"cash": [median] * 50}}
        safety = {"chance_constraints": [
            {"metric": "cash", "condition": "below", "threshold": 1e9, "max_prob": 0.0}]}
        return kernel.compute_fitness(mc, {"components": [{"expr": "cash_median"}]},
                                      safety if with_safety else None)

    def test_violation_lowers_positive_fitness(self):
        self.assertLess(self._fit(100.0, True), self._fit(100.0, False))

    def test_violation_lowers_negative_fitness(self):
        # Pre-fix: -100 * 0.7 = -70 ranked ABOVE the unpenalized -100.
        self.assertLess(self._fit(-100.0, True), self._fit(-100.0, False))
        self.assertAlmostEqual(self._fit(-100.0, True), -130.0)


class TestPriorStrengthFlowsThrough(unittest.TestCase):
    def test_feed_strength_sets_beta_pseudo_count(self):
        weak = polymarket.prior_variable(0.6, strength=5)
        strong = polymarket.prior_variable(0.6, strength=200)
        _, rep_w = bayesian.update_parameter(weak, [(8, 10)])
        _, rep_s = bayesian.update_parameter(strong, [(8, 10)])
        self.assertAlmostEqual(rep_w["alpha_prior"] + rep_w["beta_prior"], 5.0, places=1)
        self.assertAlmostEqual(rep_s["alpha_prior"] + rep_s["beta_prior"], 200.0, places=1)
        # a strong prior moves far less toward the 0.8 observed rate
        self.assertGreater(rep_w["posterior_mean"], rep_s["posterior_mean"])
        self.assertAlmostEqual(rep_s["posterior_mean"], 0.6, delta=0.02)

    def test_default_pseudo_count_unchanged_without_declaration(self):
        var = {"distribution": "triangular", "params": {"low": 0.4, "mode": 0.6, "high": 0.8}}
        _, rep = bayesian.update_parameter(var, [(8, 10)], method="beta_binomial")
        self.assertAlmostEqual(rep["alpha_prior"] + rep["beta_prior"], 10.0, places=1)

    def test_nonpositive_strength_rejected(self):
        var = polymarket.prior_variable(0.6, strength=20)
        var["calibration"]["prior_strength"] = 0
        with self.assertRaises(ValueError):
            bayesian.update_parameter(var, [(8, 10)])


class TestStatsPrecision(unittest.TestCase):
    def test_unit_scale_metric_keeps_four_decimals(self):
        cfg = kernel.DomainConfig(_cfg(
            n_simulations=500,
            parameters={"p": {"distribution": "normal", "params": {"mean": 0.1234, "std": 1e-6}}},
            step_logic=[{"target": "y", "expr": "p"}],
            metrics={"p_out": {"expr": "p", "format": "percent"}},
        ))
        mc = kernel.run_monte_carlo(cfg, seed=1)
        self.assertAlmostEqual(mc["stats"]["p_out"]["mean"], 0.1234, places=4)
        self.assertAlmostEqual(mc["stats"]["p_out"]["p90"], 0.1234, places=4)


class TestPoissonLargeLambda(unittest.TestCase):
    def test_mean_tracks_lambda(self):
        import random
        random.seed(0)
        draws = [kernel.SAMPLERS["poisson"]({"lambda": 2000}) for _ in range(200)]
        self.assertAlmostEqual(statistics.mean(draws), 2000, delta=15)

    def test_small_lambda_still_sane(self):
        import random
        random.seed(0)
        draws = [kernel.SAMPLERS["poisson"]({"lambda": 3}) for _ in range(4000)]
        self.assertAlmostEqual(statistics.mean(draws), 3, delta=0.15)
        self.assertEqual(kernel.SAMPLERS["poisson"]({"lambda": 0}), 0.0)


class TestConcurrentReproducibility(unittest.TestCase):
    def test_threads_with_same_seed_match_sequential(self):
        cfg = kernel.DomainConfig(_cfg(n_simulations=2000))
        expected = kernel.run_monte_carlo(cfg, seed=11)["stats"]["y_out"]
        results = []
        def go():
            results.append(kernel.run_monte_carlo(cfg, seed=11)["stats"]["y_out"])
        threads = [threading.Thread(target=go) for _ in range(6)]
        for t in threads: t.start()
        for t in threads: t.join()
        for r in results:
            self.assertEqual(r, expected)


class TestEvolveDeterminism(unittest.TestCase):
    CFG = {
        "name": "ga", "n_simulations": 100, "n_steps": 1, "seed": 5,
        "controls": {"lever": {"distribution": "fixed", "params": {"value": 2.0}}},
        "parameters": {"noise": {"distribution": "normal", "params": {"mean": 0, "std": 1}}},
        "step_logic": [{"target": "y", "expr": "-(lever - 3) ** 2 + noise"}],
        "metrics": {"y_out": {"expr": "y"}},
        "fitness": {"components": [{"expr": "y_out_mean", "weight": 1.0}]},
        "tunable": [{"path": "controls.lever.params.value", "range": [0, 6]}],
    }

    def test_seeded_evolve_is_reproducible(self):
        a = kernel.evolve(copy.deepcopy(self.CFG), generations=3, population=5, verbose=False)
        b = kernel.evolve(copy.deepcopy(self.CFG), generations=3, population=5, verbose=False)
        self.assertEqual(a["best"]["fitness"], b["best"]["fitness"])
        self.assertEqual(a["best_controls"], b["best_controls"])
        self.assertEqual(a["manifest"]["extra"]["ga_seed"], 5)

    def test_worker_accepts_legacy_four_tuple(self):
        cfg = copy.deepcopy(self.CFG)
        out = kernel._worker((cfg, cfg["fitness"], None, "legacy"))
        self.assertIn("fitness", out)


class TestVersionSingleSource(unittest.TestCase):
    def test_manifest_and_package_agree(self):
        import importlib
        pkg_init = os.path.join(os.path.dirname(__file__), "..", "__init__.py")
        import ast
        with open(pkg_init) as f:
            tree = ast.parse(f.read())
        init_version = next(n.value.value for n in ast.walk(tree)
                            if isinstance(n, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
        self.assertEqual(kernel.KERNEL_VERSION, init_version)
        self.assertEqual(kernel.make_manifest({"a": 1}, 10, 1)["kernel_version"], init_version)


if __name__ == "__main__":
    unittest.main()

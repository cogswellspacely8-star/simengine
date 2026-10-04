#!/usr/bin/env python3
"""beta / gamma / categorical / empirical samplers (2026-10-03 review, phase 1).

Moments are checked against closed forms with seeded draws; the copula path is
checked for correlation recovery; validation, the deterministic baseline and
the JSON Schema contract are checked for each new distribution.
"""

import json
import os
import random
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

N = 20000


def _draws(dist, params, n=N, seed=7):
    random.seed(seed)
    return [kernel.SAMPLERS[dist](params) for _ in range(n)]


class TestMoments(unittest.TestCase):
    def test_beta(self):
        a, b = 2.0, 5.0
        d = _draws("beta", {"alpha": a, "beta": b})
        self.assertAlmostEqual(statistics.mean(d), a / (a + b), delta=0.01)
        self.assertAlmostEqual(statistics.pvariance(d), a * b / ((a + b) ** 2 * (a + b + 1)), delta=0.003)
        self.assertTrue(all(0 <= x <= 1 for x in d))

    def test_beta_rescaled(self):
        d = _draws("beta", {"alpha": 2, "beta": 2, "low": 10, "high": 20})
        self.assertAlmostEqual(statistics.mean(d), 15, delta=0.1)
        self.assertTrue(all(10 <= x <= 20 for x in d))

    def test_gamma_scale_and_rate_agree(self):
        d1 = _draws("gamma", {"shape": 3.0, "scale": 2.0})
        d2 = _draws("gamma", {"shape": 3.0, "rate": 0.5})
        self.assertAlmostEqual(statistics.mean(d1), 6.0, delta=0.15)
        self.assertAlmostEqual(statistics.pvariance(d1), 12.0, delta=1.0)
        self.assertEqual(d1, d2)

    def test_categorical_frequencies(self):
        d = _draws("categorical", {"values": [1, 2, 3], "probs": [0.2, 0.3, 0.5]})
        for v, p in ((1, 0.2), (2, 0.3), (3, 0.5)):
            self.assertAlmostEqual(d.count(v) / N, p, delta=0.015)

    def test_categorical_uniform_when_no_probs(self):
        d = _draws("categorical", {"values": [10, 20]})
        self.assertAlmostEqual(d.count(10) / N, 0.5, delta=0.015)

    def test_empirical_bootstrap_and_jitter(self):
        vals = [1, 2, 3, 4, 10]
        d = _draws("empirical", {"values": vals})
        self.assertAlmostEqual(statistics.mean(d), 4.0, delta=0.1)
        self.assertEqual(set(d), set(vals))
        dj = _draws("empirical", {"values": vals, "jitter": 0.5})
        self.assertAlmostEqual(statistics.mean(dj), 4.0, delta=0.1)
        self.assertGreater(len(set(dj)), 100)


class TestCopulaOnNewDistributions(unittest.TestCase):
    def _corr(self, a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)
        return cov / (statistics.pstdev(a) * statistics.pstdev(b))

    def _run(self, vdef):
        cfg = kernel.DomainConfig({
            "name": "c", "n_simulations": 3000, "n_steps": 1,
            "parameters": {"a": vdef,
                           "b": {"distribution": "normal", "params": {"mean": 0, "std": 1}}},
            "correlations": [{"vars": ["a", "b"], "rho": 0.8}],
            "step_logic": [{"target": "y", "expr": "a"}],
            "metrics": {"a_out": {"expr": "a"}, "b_out": {"expr": "b"}},
        })
        mc = kernel.run_monte_carlo(cfg, seed=2)
        return mc["raw_metrics"]["a_out"], mc["raw_metrics"]["b_out"]

    def test_beta_keeps_marginal_and_correlation(self):
        a, b = self._run({"distribution": "beta", "params": {"alpha": 2, "beta": 5}})
        self.assertAlmostEqual(statistics.mean(a), 2 / 7, delta=0.02)
        self.assertGreater(self._corr(a, b), 0.6)

    def test_gamma_keeps_marginal_and_correlation(self):
        a, b = self._run({"distribution": "gamma", "params": {"shape": 3, "scale": 2}})
        self.assertAlmostEqual(statistics.mean(a), 6, delta=0.3)
        self.assertGreater(self._corr(a, b), 0.6)

    def test_categorical_and_empirical_follow_z(self):
        a, b = self._run({"distribution": "categorical", "params": {"values": [0, 1, 2], "probs": [0.3, 0.4, 0.3]}})
        self.assertGreater(self._corr(a, b), 0.5)
        a, b = self._run({"distribution": "empirical", "params": {"values": list(range(100))}})
        self.assertGreater(self._corr(a, b), 0.7)

    def test_quantile_table_does_not_disturb_seeded_stream(self):
        kernel._QUANTILE_TABLE_CACHE.clear()
        first = self._run({"distribution": "beta", "params": {"alpha": 3, "beta": 3}})
        kernel._QUANTILE_TABLE_CACHE.clear()
        second = self._run({"distribution": "beta", "params": {"alpha": 3, "beta": 3}})
        self.assertEqual(first, second)


class TestBaselineAndValidation(unittest.TestCase):
    def _cfg(self, vdef):
        return {"name": "v", "n_steps": 1, "n_simulations": 20,
                "parameters": {"a": vdef},
                "step_logic": [{"target": "y", "expr": "a"}],
                "metrics": {"m": {"expr": "y"}}}

    def test_baseline_point_estimates(self):
        cases = [
            ({"distribution": "beta", "params": {"alpha": 2, "beta": 6}}, 0.25),
            ({"distribution": "gamma", "params": {"shape": 2, "rate": 0.5}}, 4.0),
            ({"distribution": "categorical", "params": {"values": [1, 2, 3], "probs": [0.1, 0.7, 0.2]}}, 2),
            ({"distribution": "empirical", "params": {"values": [5, 1, 9]}}, 5),
        ]
        for vdef, expected in cases:
            with self.subTest(dist=vdef["distribution"]):
                r = diagnostics.deterministic_baseline(kernel.DomainConfig(self._cfg(vdef)))
                self.assertAlmostEqual(r["final_metrics"]["m"], expected, places=6)

    def test_valid_configs_pass(self):
        for vdef in (
            {"distribution": "beta", "params": {"alpha": 2, "beta": 6}},
            {"distribution": "gamma", "params": {"shape": 2, "scale": 1.5}},
            {"distribution": "categorical", "params": {"values": [1, 2], "probs": [0.5, 0.5]}},
            {"distribution": "empirical", "params": {"values": [1.0, 2.0, 3.0], "jitter": 0.1}},
        ):
            with self.subTest(dist=vdef["distribution"]):
                self.assertEqual(validation.validate_config(self._cfg(vdef)), [])

    def test_bad_params_named(self):
        cases = [
            ({"distribution": "beta", "params": {"alpha": 2}}, "missing required param 'beta'"),
            ({"distribution": "beta", "params": {"alpha": 0, "beta": 1}}, "must be positive"),
            ({"distribution": "gamma", "params": {"shape": 2}}, "provide 'scale' or 'rate'"),
            ({"distribution": "categorical", "params": {"values": [1, 2], "probs": [1]}}, "same length"),
            ({"distribution": "categorical", "params": {"values": []}}, "non-empty list"),
            ({"distribution": "empirical", "params": {"values": [1, "x"]}}, "must all be numbers"),
            ({"distribution": "normal", "params": {"mean": 1}}, "missing required param 'std'"),
        ]
        for vdef, needle in cases:
            with self.subTest(dist=vdef["distribution"], needle=needle):
                errs = validation.validate_config(self._cfg(vdef))
                self.assertTrue(any(needle in e for e in errs), errs)

    def test_late_binding_satisfies_required(self):
        cfg = self._cfg({"distribution": "beta", "params": {"alpha": "$y", "beta": 2}})
        cfg["initial_state"] = {"y": 2}
        self.assertEqual(validation.validate_config(cfg), [])

    @unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_schema_accepts_new_distributions_and_rejects_bad(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "schema", "domain.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)
        v = jsonschema.Draft202012Validator(schema) if hasattr(jsonschema, "Draft202012Validator") else jsonschema.Draft7Validator(schema)
        good = [
            {"distribution": "beta", "params": {"alpha": 2, "beta": 6}},
            {"distribution": "gamma", "params": {"shape": 2, "rate": 0.5}},
            {"distribution": "categorical", "params": {"values": [1, 2, 3], "probs": [0.2, 0.3, 0.5]}},
            {"distribution": "empirical", "params": {"values": [1, 2, 3], "jitter": 0.1}},
        ]
        for vdef in good:
            with self.subTest(dist=vdef["distribution"]):
                self.assertEqual(list(v.iter_errors(self._cfg(vdef))), [])
        bad = [
            {"distribution": "beta", "params": {"alpha": 2}},
            {"distribution": "gamma", "params": {"shape": 2}},
            {"distribution": "categorical", "params": {"probs": [1]}},
            {"distribution": "empirical", "params": {"values": ["a"]}},
        ]
        for vdef in bad:
            with self.subTest(dist=vdef["distribution"]):
                self.assertTrue(list(v.iter_errors(self._cfg(vdef))))


if __name__ == "__main__":
    unittest.main()

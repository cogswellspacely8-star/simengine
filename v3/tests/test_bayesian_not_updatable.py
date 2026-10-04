#!/usr/bin/env python3
"""update_config on a variable with no conjugate mapping must leave it alone.

Before: the updaters returned the bare params dict, update_config unpacked
its KEYS, and the config came back with params == 'low' (a string) and a
report of 'high'. Silent config corruption through /api/update.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bayesian


class TestNotUpdatable(unittest.TestCase):
    def _cfg(self, vdef):
        return {"name": "t", "parameters": {"u": vdef}}

    def test_uniform_left_unchanged_with_skipped_report(self):
        cfg = self._cfg({"distribution": "uniform", "params": {"low": 0, "high": 1}})
        updated, report = bayesian.update_config(cfg, {"u": [0.4, 0.5]})
        self.assertEqual(updated["parameters"]["u"]["params"], {"low": 0, "high": 1})
        self.assertTrue(report["u"]["skipped"])
        self.assertIn("no conjugate mapping", report["u"]["reason"])

    def test_categorical_and_empirical_left_unchanged(self):
        for vdef in ({"distribution": "categorical", "params": {"values": [1, 2]}},
                     {"distribution": "empirical", "params": {"values": [1.0, 2.0]}}):
            with self.subTest(dist=vdef["distribution"]):
                updated, report = bayesian.update_config(self._cfg(vdef), {"u": [1, 2]})
                self.assertEqual(updated["parameters"]["u"]["params"], vdef["params"])
                self.assertTrue(report["u"]["skipped"])

    def test_each_updater_returns_a_pair(self):
        for fn in (bayesian.beta_binomial_update, bayesian.gamma_poisson_update,
                   bayesian.normal_normal_update):
            with self.subTest(fn=fn.__name__):
                out = fn({"low": 0, "high": 1}, [0.5])
                self.assertIsInstance(out, tuple)
                self.assertEqual(len(out), 2)
                self.assertTrue(out[1]["skipped"])


if __name__ == "__main__":
    unittest.main()

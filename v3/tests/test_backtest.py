#!/usr/bin/env python3
"""
Test suite for the historical calibration backtest harness (backtest.py).
Uses only Python stdlib unittest — zero external dependencies.

The harness itself is offline: it reads committed CSV snapshots. These tests
never touch the network.
"""

import os
import sys
import math
import tempfile
import unittest

# Make v3 package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import backtest
import validation


def write_csv(path, rows, header="observation_date,TEST"):
    with open(path, "w") as f:
        f.write(header + "\n")
        for date, value in rows:
            f.write(f"{date},{value}\n")


class TestLoadFredCsv(unittest.TestCase):
    def test_parses_dates_and_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TEST.csv")
            write_csv(p, [("2020-01-01", "3.5"), ("2020-02-01", "3.6")])
            series = backtest.load_fred_csv(p)
        self.assertEqual(series, [("2020-01-01", 3.5), ("2020-02-01", 3.6)])

    def test_skips_missing_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TEST.csv")
            write_csv(p, [("2020-01-01", "3.5"), ("2020-02-01", "."),
                          ("2020-03-01", ""), ("2020-04-01", "4.0")])
            series = backtest.load_fred_csv(p)
        self.assertEqual([v for _, v in series], [3.5, 4.0])


class TestTransforms(unittest.TestCase):
    def test_diffs(self):
        self.assertEqual(backtest.diffs([1.0, 3.0, 2.5]), [2.0, -0.5])

    def test_log_pct_changes(self):
        out = backtest.log_pct_changes([100.0, 101.0])
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0], 100.0 * math.log(101.0 / 100.0))

    def test_log_pct_changes_requires_positive(self):
        with self.assertRaises(ValueError):
            backtest.log_pct_changes([100.0, 0.0])


class TestForecastConfig(unittest.TestCase):
    def test_config_passes_engine_validation(self):
        window = [0.1 * i - 0.5 for i in range(24)]
        cfg = backtest.build_forecast_config(window, ">", 0.0, n_sims=500)
        self.assertEqual(validation.validate_config(cfg), [])

    def test_zero_variance_window_gets_epsilon_std(self):
        cfg = backtest.build_forecast_config([2.0] * 24, ">", 0.0, n_sims=500)
        std = cfg["parameters"]["z"]["params"]["std"]
        self.assertGreater(std, 0.0)


class TestForecastProb(unittest.TestCase):
    def test_symmetric_window_gives_half(self):
        # mean 0, std 1 window; P(z > 0) should be ~0.5
        window = [1.0, -1.0] * 30
        p = backtest.forecast_prob(window, ">", 0.0, n_sims=2000, seed=7)
        self.assertGreater(p, 0.42)
        self.assertLess(p, 0.58)

    def test_far_threshold_gives_near_zero(self):
        window = [1.0, -1.0] * 30
        p = backtest.forecast_prob(window, ">", 50.0, n_sims=1000, seed=7)
        self.assertLess(p, 0.01)

    def test_deterministic_under_seed(self):
        window = [0.5, -0.25, 0.1, -0.4] * 10
        a = backtest.forecast_prob(window, "<", 0.0, n_sims=1000, seed=42)
        b = backtest.forecast_prob(window, "<", 0.0, n_sims=1000, seed=42)
        self.assertEqual(a, b)


class TestClimatology(unittest.TestCase):
    def test_laplace_smoothing_avoids_certainty(self):
        self.assertGreater(backtest.climatology_prob([0] * 50), 0.0)
        self.assertLess(backtest.climatology_prob([1] * 50), 1.0)

    def test_base_rate_recovered(self):
        p = backtest.climatology_prob([1, 0, 1, 0] * 25)
        self.assertAlmostEqual(p, (50 + 1) / (100 + 2))


class TestRunTask(unittest.TestCase):
    def _synthetic_task(self, d):
        # A noisy alternating series: increments are +1/-1 with jitter, so the
        # "rises next month" event is learnable but not degenerate.
        import random as _r
        _r.seed(3)
        rows, v = [], 100.0
        for i in range(80):
            v += (1 if i % 2 == 0 else -1) + _r.uniform(-0.2, 0.2)
            rows.append((f"19{70 + i // 12}-{i % 12 + 1:02d}-01", f"{v:.4f}"))
        p = os.path.join(d, "SYN.csv")
        write_csv(p, rows)
        return {
            "csv": "SYN.csv",
            "transform": "diff",
            "op": ">",
            "threshold": 0.0,
            "question": "does SYN rise next month?",
        }

    def test_returns_scored_result(self):
        with tempfile.TemporaryDirectory() as d:
            spec = self._synthetic_task(d)
            res = backtest.run_task("syn_rises", spec, data_dir=d,
                                    window=24, n_sims=400, seed=11)
        self.assertGreater(res["n"], 10)
        self.assertGreaterEqual(res["brier"], 0.0)
        self.assertLessEqual(res["brier"], 1.0)
        self.assertIn("ece", res)
        self.assertIn("climatology_brier", res)
        self.assertIn("brier_skill_vs_climatology", res)
        self.assertEqual(res["n"], len(res["forecasts"]))
        # Walk-forward contract: every forecast dated, prob in [0,1], outcome binary
        for f in res["forecasts"]:
            self.assertGreaterEqual(f["p"], 0.0)
            self.assertLessEqual(f["p"], 1.0)
            self.assertIn(f["outcome"], (0, 1))

    def test_limit_caps_origins(self):
        with tempfile.TemporaryDirectory() as d:
            spec = self._synthetic_task(d)
            res = backtest.run_task("syn_rises", spec, data_dir=d,
                                    window=24, n_sims=200, seed=11, limit=5)
        self.assertEqual(res["n"], 5)


class TestRealSnapshotSlice(unittest.TestCase):
    """A tiny slice against the committed FRED snapshots (offline, fast)."""

    def test_unrate_slice_runs(self):
        data_dir = backtest.DEFAULT_DATA_DIR
        if not os.path.exists(os.path.join(data_dir, "UNRATE.csv")):
            self.skipTest("no committed UNRATE snapshot")
        res = backtest.run_task("unrate_rises", backtest.TASKS["unrate_rises"],
                                data_dir=data_dir, window=120, n_sims=300,
                                seed=1, limit=4)
        self.assertEqual(res["n"], 4)
        for f in res["forecasts"]:
            self.assertTrue(0.0 <= f["p"] <= 1.0)


if __name__ == "__main__":
    unittest.main()

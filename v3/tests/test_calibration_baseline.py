#!/usr/bin/env python3
"""Ledger: baseline column + skill, per-model grouping, CRPS resolution,
in-place schema migration (2026-10-03 review, phase 3)."""

import json
import os
import random
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import calibration
from calibration import CalibrationLedger

OLD_SCHEMA = """
CREATE TABLE forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL,
    predicted_prob REAL NOT NULL, config_hash TEXT, metric TEXT, samples_json TEXT,
    created_at TEXT NOT NULL, resolve_by TEXT, resolved_at TEXT, outcome INTEGER);
"""


class TestMigration(unittest.TestCase):
    def test_old_ledger_opens_and_gains_columns(self):
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        conn = sqlite3.connect(path)
        conn.execute(OLD_SCHEMA)
        conn.execute("INSERT INTO forecasts (question, predicted_prob, created_at, outcome) "
                     "VALUES ('legacy', 0.4, '2026-06-01', 1)")
        conn.commit(); conn.close()
        led = CalibrationLedger(path)
        cols = {r[1] for r in led.conn.execute("PRAGMA table_info(forecasts)")}
        self.assertTrue({"baseline_prob", "baseline_source", "model", "outcome_value"} <= cols)
        rows = led.all_forecasts()
        self.assertEqual(rows[0]["question"], "legacy")
        self.assertIsNone(rows[0]["baseline_prob"])
        self.assertEqual(led.score()["n"], 1)
        self.assertIsNone(led.score()["baseline"])
        # idempotent
        CalibrationLedger(path)


class TestBaselineSkill(unittest.TestCase):
    def setUp(self):
        self.led = CalibrationLedger()

    def test_skill_against_recorded_baseline(self):
        # model sharper than baseline on 4 outcomes
        for p, b, o in ((0.8, 0.6, 1), (0.2, 0.4, 0), (0.7, 0.5, 1), (0.3, 0.5, 0)):
            fid = self.led.record("q", p, baseline_prob=b, baseline_source="market", model="m1")
            self.led.resolve(fid, o)
        s = self.led.score()
        base = s["baseline"]
        self.assertEqual(base["n"], 4)
        self.assertAlmostEqual(base["brier"], (0.16 + 0.16 + 0.25 + 0.25) / 4, places=4)
        self.assertAlmostEqual(base["model_brier_on_same"], (0.04 + 0.04 + 0.09 + 0.09) / 4, places=4)
        self.assertGreater(base["brier_skill"], 0.5)
        self.assertEqual(base["sources"], ["market"])

    def test_rows_without_baseline_are_excluded_from_skill_not_from_brier(self):
        a = self.led.record("q", 0.9, baseline_prob=0.5); self.led.resolve(a, 1)
        b = self.led.record("q", 0.1); self.led.resolve(b, 1)  # bad, no baseline
        s = self.led.score()
        self.assertEqual(s["n"], 2)
        self.assertEqual(s["baseline"]["n"], 1)
        self.assertAlmostEqual(s["baseline"]["model_brier_on_same"], 0.01, places=4)

    def test_by_model_groups(self):
        for model, p, o in (("a", 0.9, 1), ("a", 0.8, 1), ("b", 0.9, 0), (None, 0.5, 1)):
            fid = self.led.record("q", p, model=model, baseline_prob=0.5)
            self.led.resolve(fid, o)
        groups = {g["model"]: g for g in self.led.by_model()}
        self.assertEqual(set(groups), {"a", "b", "unspecified"})
        self.assertEqual(groups["a"]["n"], 2)
        self.assertAlmostEqual(groups["a"]["baseline"]["brier_skill"], 0.9, places=4)  # 1 - 0.025/0.25
        self.assertLess(groups["b"]["baseline"]["brier_skill"], 0)
        report = self.led.calibration_report()
        self.assertEqual(len(report["by_model"]), 3)
        self.assertIn("continuous", report)

    def test_baseline_validation(self):
        with self.assertRaises(ValueError):
            self.led.record("q", 0.5, baseline_prob=1.5)

    def test_pending_filter(self):
        self.led.record("q1", 0.5, config_hash="h1", model="m")
        f2 = self.led.record("q2", 0.5, config_hash="h1", model="m")
        self.led.record("q3", 0.5, config_hash="h2")
        self.led.resolve(f2, 1)
        self.assertEqual([r["question"] for r in self.led.pending(config_hash="h1")], ["q1"])
        self.assertEqual(len(self.led.pending()), 2)


class TestCRPS(unittest.TestCase):
    def test_fast_crps_matches_brute_force(self):
        random.seed(1)
        for _ in range(20):
            xs = [random.gauss(0, 3) for _ in range(random.randint(1, 40))]
            y = random.gauss(0, 3)
            n = len(xs)
            brute = (sum(abs(x - y) for x in xs) / n
                     - sum(abs(a - b) for a in xs for b in xs) / (2 * n * n))
            self.assertAlmostEqual(calibration.crps_sample(xs, y), brute, places=10)

    def test_point_forecast_reduces_to_abs_error(self):
        self.assertAlmostEqual(calibration.crps_sample([3.0], 5.0), 2.0)

    def test_continuous_report_from_samples_and_outcome_value(self):
        led = CalibrationLedger()
        random.seed(2)
        samples = [random.gauss(10, 2) for _ in range(2000)]
        fid = led.record("x > 11?", 0.3, samples=samples)
        led.resolve(fid, 0, outcome_value=10.4)
        rep = led.continuous_report()
        self.assertEqual(rep["n"], 1)
        self.assertGreater(rep["crps"], 0)
        self.assertLess(rep["crps"], rep["point_mae"] + 2.0)
        self.assertEqual(led.resolved()[0]["outcome_value"], 10.4)
        # rows without samples or outcome_value are ignored
        g = led.record("y", 0.5); led.resolve(g, 1)
        self.assertEqual(led.continuous_report()["n"], 1)


if __name__ == "__main__":
    unittest.main()

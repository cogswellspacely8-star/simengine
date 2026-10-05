#!/usr/bin/env python3
"""forecast_buckets: record a set of bucket forecasts, resolve them from the
realized state by evaluating each metric's own expression, report skill."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import forecast_buckets as fb
import validation
from calibration import CalibrationLedger

V3 = os.path.join(os.path.dirname(__file__), "..")
DOMAIN = os.path.join(V3, "domains", "temp_high_buckets.json")
BASELINE = os.path.join(V3, "examples", "temp_high_buckets_baseline.json")


class TestBucketLoop(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "f.db")

    def test_domain_is_valid_and_buckets_partition(self):
        with open(DOMAIN) as f:
            data = json.load(f)
        self.assertEqual(validation.validate_config(data), [])
        res = fb.cmd_record(DOMAIN, db=self.db, n_sims=4000)
        self.assertEqual(len(res["forecasts"]), 5)
        self.assertAlmostEqual(res["model_mass"], 1.0, places=3)
        for r in res["forecasts"]:
            self.assertIsNotNone(r["ci95"])
            self.assertLessEqual(r["ci95"][0], r["p_model"])
            self.assertGreaterEqual(r["ci95"][1], r["p_model"])

    def test_record_with_baseline_then_resolve_and_score(self):
        rec = fb.cmd_record(DOMAIN, baseline=BASELINE, source="market", model="temp_v1",
                            resolve_by="2026-10-05", db=self.db, n_sims=4000)
        self.assertAlmostEqual(rec["baseline_mass"], 1.0, places=3)
        self.assertTrue(all(r["p_baseline"] is not None for r in rec["forecasts"]))
        led = CalibrationLedger(self.db)
        self.assertEqual(len(led.pending(config_hash=rec["config_hash"])), 5)
        self.assertEqual(led.pending()[0]["model"], "temp_v1")
        self.assertEqual(led.pending()[0]["resolve_by"], "2026-10-05")

        res = fb.cmd_resolve(DOMAIN, {"actual_high": 73.4}, db=self.db)
        self.assertEqual(res["buckets_hit"], ["p_73_75"])
        self.assertEqual(res["outcome_value"], 73.4)
        self.assertEqual(sum(r["outcome"] for r in res["resolved"]), 1)
        self.assertEqual(len(led.pending()), 0)
        s = res["score"]
        self.assertEqual(s["n"], 5)
        self.assertEqual(s["baseline"]["n"], 5)
        self.assertEqual(s["baseline"]["sources"], ["market"])
        self.assertEqual(led.resolved()[0]["outcome_value"], 73.4)

        rep = fb.cmd_report(db=self.db)
        self.assertEqual(rep["n"], 5)
        self.assertEqual(rep["by_model"][0]["model"], "temp_v1")

    def test_resolve_refuses_incomplete_state(self):
        fb.cmd_record(DOMAIN, db=self.db, n_sims=500)
        with self.assertRaises(ValueError) as ctx:
            fb.cmd_resolve(DOMAIN, {"wrong_name": 70}, db=self.db)
        self.assertIn("actual_high", str(ctx.exception))
        self.assertEqual(len(CalibrationLedger(self.db).pending()), 5)  # nothing graded

    def test_resolve_with_nothing_pending_explains(self):
        res = fb.cmd_resolve(DOMAIN, {"actual_high": 70}, db=self.db)
        self.assertEqual(res["resolved"], [])
        self.assertIn("no pending forecasts", res["note"])

    def test_boundary_values_follow_half_open_buckets(self):
        fb.cmd_record(DOMAIN, db=self.db, n_sims=500)
        res = fb.cmd_resolve(DOMAIN, {"actual_high": 71.0}, db=self.db)
        self.assertEqual(res["buckets_hit"], ["p_71_73"])

    def test_cli_round_trip_json(self):
        env = dict(os.environ, SIMENGINE_LEDGER_DB=self.db)
        out = subprocess.run([sys.executable, os.path.join(V3, "forecast_buckets.py"), "--json", "record",
                              "--domain", "temp_high_buckets.json", "--n-sims", "500",
                              "--baseline", BASELINE, "--source", "market"],
                             capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        rec = json.loads(out.stdout)
        self.assertEqual(len(rec["forecasts"]), 5)
        out = subprocess.run([sys.executable, os.path.join(V3, "forecast_buckets.py"), "resolve",
                              "--domain", "temp_high_buckets.json", "--state", '{"actual_high": 68.2}'],
                             capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("p_lt_69", out.stdout)
        self.assertIn("HIT", out.stdout)
        out = subprocess.run([sys.executable, os.path.join(V3, "forecast_buckets.py"), "report"],
                             capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("vs baseline", out.stdout)

    def test_cli_bad_state_exits_2(self):
        env = dict(os.environ, SIMENGINE_LEDGER_DB=self.db)
        out = subprocess.run([sys.executable, os.path.join(V3, "forecast_buckets.py"), "resolve",
                              "--domain", "temp_high_buckets.json", "--state", "not json"],
                             capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, 2)
        self.assertIn("error:", out.stderr)


if __name__ == "__main__":
    unittest.main()

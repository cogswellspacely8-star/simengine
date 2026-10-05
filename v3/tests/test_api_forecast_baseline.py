#!/usr/bin/env python3
"""/api/forecast accepts baseline_prob / baseline_source / model; /api/resolve
accepts outcome_value; /api/forecasts reports skill vs baseline."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server


class TestForecastBaselineApi(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "forecasts.db")
        self._env = mock.patch.dict(os.environ, {"SIMENGINE_LEDGER_DB": self.db})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_round_trip_with_baseline_and_outcome_value(self):
        payload, status = server.handle_forecast_record(
            {"question": "CPI MoM > 0.25%", "predicted_prob": 0.7, "baseline_prob": 0.55,
             "baseline_source": "market", "model": "cpi_v1"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["baseline_prob"], 0.55)
        resolved, s = server.handle_resolve({"id": payload["id"], "outcome": 1, "outcome_value": 0.31})
        self.assertEqual(s, 200)
        self.assertEqual(resolved["outcome_value"], 0.31)
        self.assertEqual(resolved["score"]["baseline"]["n"], 1)
        self.assertGreater(resolved["score"]["baseline"]["brier_skill"], 0)
        listed, _ = server.handle_forecasts_list()
        self.assertEqual(listed["forecasts"][0]["model"], "cpi_v1")
        self.assertEqual(listed["calibration"]["by_model"][0]["model"], "cpi_v1")

    def test_bad_baseline_rejected(self):
        _, status = server.handle_forecast_record({"question": "q", "predicted_prob": 0.5, "baseline_prob": 2})
        self.assertEqual(status, 400)
        _, status = server.handle_forecast_record({"question": "q", "predicted_prob": 0.5, "baseline_prob": "x"})
        self.assertEqual(status, 400)

    def test_bad_outcome_value_rejected(self):
        payload, _ = server.handle_forecast_record({"question": "q", "predicted_prob": 0.5})
        _, status = server.handle_resolve({"id": payload["id"], "outcome": 1, "outcome_value": "nope"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()

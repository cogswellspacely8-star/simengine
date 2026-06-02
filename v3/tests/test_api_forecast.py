#!/usr/bin/env python3
"""Tests for the calibration-ledger API: POST /api/forecast, /api/resolve, GET /api/forecasts."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server


class TestForecastApi(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "forecasts.db")
        self._env = mock.patch.dict(os.environ, {"SIMENGINE_LEDGER_DB": self.db})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_record_list_resolve_score(self):
        payload, status = server.handle_forecast_record(
            {"question": "Spurs win the series", "predicted_prob": 0.64, "resolve_by": "2026-06-16"})
        self.assertEqual(status, 200)
        fid = payload["id"]

        listed, s2 = server.handle_forecasts_list()
        self.assertEqual(s2, 200)
        self.assertEqual(len(listed["forecasts"]), 1)
        self.assertEqual(listed["forecasts"][0]["resolve_by"], "2026-06-16")
        self.assertEqual(listed["score"]["n"], 0)  # nothing resolved yet

        resolved, s3 = server.handle_resolve({"id": fid, "outcome": 1})
        self.assertEqual(s3, 200)
        self.assertEqual(resolved["score"]["n"], 1)
        self.assertAlmostEqual(resolved["score"]["brier"], (0.64 - 1) ** 2)

    def test_rejects_bad_probability(self):
        _, status = server.handle_forecast_record({"question": "x", "predicted_prob": 1.5})
        self.assertEqual(status, 400)

    def test_requires_question(self):
        _, status = server.handle_forecast_record({"predicted_prob": 0.5})
        self.assertEqual(status, 400)

    def test_resolve_unknown_id_404(self):
        _, status = server.handle_resolve({"id": 99999, "outcome": 1})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()

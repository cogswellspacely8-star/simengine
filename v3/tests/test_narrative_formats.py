#!/usr/bin/env python3
"""Risk-warning lines render thresholds and CVaR in the metric's own format."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server


class TestRiskWarningFormats(unittest.TestCase):
    def _narrative(self, fmt, threshold, cvar, min_cvar):
        stats = {"m": {"median": 1, "p10": 0, "p90": 2, "format": fmt}}
        safety = {"all_passed": False,
                  "chance": [{"metric": "m", "condition": "above", "threshold": threshold,
                              "max_prob": 0.2, "actual_prob": 0.34, "passed": False}],
                  "cvar": [{"metric": "m", "alpha": 0.1, "min_cvar": min_cvar,
                            "actual_cvar": cvar, "passed": False}]}
        return server.generate_narrative(stats, safety, {})

    def test_percent_metric_threshold_not_rounded_to_zero(self):
        text = self._narrative("percent", 0.20, 0.31, 0.25)
        self.assertIn("above 20.0%", text)
        self.assertNotIn("above 0 ", text)
        self.assertIn("averages 31.0% (limit: 25.0%)", text)

    def test_number_metric_has_no_dollar_sign(self):
        text = self._narrative("number", 80, 74.2, 80)
        self.assertNotIn("$", text)
        self.assertIn("averages 74.20 (limit: 80.00)", text)

    def test_dollar_metric_keeps_dollar_sign(self):
        text = self._narrative("dollar", 60000, -30957, -25000)
        self.assertIn("above $60,000", text)
        self.assertIn("averages $-30,957 (limit: $-25,000)", text)

    def test_borderline_note_still_present(self):
        stats = {"m": {"median": 1, "p10": 0, "p90": 2, "format": "number"}}
        safety = {"all_passed": False, "cvar": [],
                  "chance": [{"metric": "m", "condition": "below", "threshold": 0,
                              "max_prob": 0.15, "actual_prob": 0.152, "passed": False,
                              "borderline": True, "actual_prob_ci95": [0.142, 0.163]}]}
        self.assertIn("borderline", server.generate_narrative(stats, safety, {}))


if __name__ == "__main__":
    unittest.main()

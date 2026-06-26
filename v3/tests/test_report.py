#!/usr/bin/env python3
"""Standalone export-report generation.

Must not crash when a domain defines no fitness objective (fitness is null), and
must headline a binary/indicator metric as a probability rather than its 0/100
median.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server


def _results(fitness):
    return {
        "domain": "Test", "n_simulations": 1000, "elapsed": 0.1,
        "narrative": "n/a", "safety": {},
        "fitness": fitness,
        "stats": {
            "pct_chance": {"mean": 33.8, "median": 0.0, "std": 47.0,
                           "p10": 0.0, "p25": 0.0, "p75": 100.0, "p90": 100.0,
                           "format": "number", "binary_prob": 0.338},
            "profit": {"mean": 1000.0, "median": 980.0, "std": 200.0,
                       "p10": 700.0, "p25": 850.0, "p75": 1150.0, "p90": 1300.0,
                       "format": "dollar"},
        },
    }


class TestExportReport(unittest.TestCase):
    def test_no_fitness_does_not_crash(self):
        html = server.generate_report_html(_results(None), {})  # must NOT raise
        self.assertIn("Test", html)

    def test_with_fitness_still_renders(self):
        html = server.generate_report_html(_results(42.5), {})
        self.assertIn("42.5", html)

    def test_binary_metric_shows_probability(self):
        html = server.generate_report_html(_results(None), {})
        self.assertIn("34% chance", html)


if __name__ == "__main__":
    unittest.main()

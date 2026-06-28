#!/usr/bin/env python3
"""Static-contract guards for the calibration UI (single-file, no browser harness).

Pins the capture affordance (Track this forecast) and the gated reliability
diagram against silent regression.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

HTML = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'index.html')).read()


class TestCaptureUI(unittest.TestCase):
    def test_track_button_present(self):
        self.assertIn("Track this forecast", HTML)

    def test_track_functions_present(self):
        self.assertIn("function openTrackForecast(", HTML)
        self.assertIn("function submitTrackForecast(", HTML)

    def test_track_posts_metric(self):
        self.assertIn("predicted_prob", HTML)
        self.assertIn("metric: metric", HTML)


if __name__ == "__main__":
    unittest.main()

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

    def test_track_posts_metric_and_resolve_by(self):
        self.assertIn("predicted_prob", HTML)
        self.assertIn("metric: metric", HTML)
        self.assertIn("resolve_by: by", HTML)

    def test_uses_quote_safe_escaper_not_attribute_interpolation(self):
        # The metric in onclick must go through the JS-string-safe escaper, and
        # the modal's question input value must be set via JS (not interpolated
        # into a quoted attribute, where a quote in the question would break it).
        self.assertIn("function jsStr(", HTML)
        self.assertIn("openTrackForecast('${jsStr(", HTML)
        self.assertIn("getElementById('track-q').value = q", HTML)

    def test_ask_flow_passes_its_own_question(self):
        self.assertIn("askLastQuestion", HTML)


class TestVizUI(unittest.TestCase):
    def test_draw_reliability_present(self):
        self.assertIn("function drawReliability(", HTML)

    def test_gate_copy_present(self):
        self.assertIn("calibration curve unlocks at", HTML)

    def test_reliability_canvas_present(self):
        self.assertIn("rel-canvas", HTML)


if __name__ == "__main__":
    unittest.main()

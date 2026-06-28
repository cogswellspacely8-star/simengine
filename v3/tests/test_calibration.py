#!/usr/bin/env python3
"""
Test suite for the calibration ledger and scoring functions (calibration.py).
Uses only Python stdlib unittest — zero external dependencies.
"""

import os
import sys
import math
import unittest

# Make v3 package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import calibration


# ---------------------------------------------------------------------------
# Proper scoring rules
# ---------------------------------------------------------------------------
class TestScoringFunctions(unittest.TestCase):
    def test_brier_score_perfect_is_zero(self):
        self.assertEqual(calibration.brier_score([1.0, 0.0], [1, 0]), 0.0)

    def test_brier_score_half_on_certain_outcome(self):
        self.assertAlmostEqual(calibration.brier_score([0.5], [1]), 0.25)

    def test_brier_score_known_value(self):
        # ((0.7-1)^2 + (0.3-0)^2) / 2 = (0.09 + 0.09) / 2 = 0.09
        self.assertAlmostEqual(calibration.brier_score([0.7, 0.3], [1, 0]), 0.09)

    def test_brier_score_worst_case_is_one(self):
        self.assertAlmostEqual(calibration.brier_score([0.0], [1]), 1.0)

    def test_brier_score_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            calibration.brier_score([0.5, 0.5], [1])

    def test_brier_score_empty_raises(self):
        with self.assertRaises(ValueError):
            calibration.brier_score([], [])

    def test_log_loss_half_is_ln2(self):
        self.assertAlmostEqual(calibration.log_loss([0.5], [1]), math.log(2))

    def test_log_loss_confident_correct_near_zero(self):
        self.assertAlmostEqual(calibration.log_loss([1.0], [1]), 0.0, places=10)

    def test_log_loss_confident_wrong_is_large_but_finite(self):
        # clamped away from 0/1 so it stays finite
        val = calibration.log_loss([0.0], [1])
        self.assertGreater(val, 10)
        self.assertTrue(math.isfinite(val))

    def test_crps_deterministic_is_absolute_error(self):
        self.assertAlmostEqual(calibration.crps_sample([5.0], 3.0), 2.0)

    def test_crps_perfect_is_zero(self):
        self.assertAlmostEqual(calibration.crps_sample([5.0], 5.0), 0.0)

    def test_crps_two_point_sample_known_value(self):
        # first term = (|3-4| + |5-4|)/2 = 1.0
        # second term = (1/(2*4)) * (0 + 2 + 2 + 0) = 0.5
        # CRPS = 1.0 - 0.5 = 0.5
        self.assertAlmostEqual(calibration.crps_sample([3.0, 5.0], 4.0), 0.5)

    def test_crps_empty_raises(self):
        with self.assertRaises(ValueError):
            calibration.crps_sample([], 1.0)


# ---------------------------------------------------------------------------
# Forecast ledger
# ---------------------------------------------------------------------------
class TestCalibrationLedger(unittest.TestCase):
    def setUp(self):
        self.ledger = calibration.CalibrationLedger(":memory:")

    def test_record_returns_integer_id(self):
        fid = self.ledger.record("Will X happen?", 0.7)
        self.assertIsInstance(fid, int)

    def test_score_over_resolved_forecasts(self):
        i1 = self.ledger.record("q1", 0.8)
        self.ledger.resolve(i1, 1)
        i2 = self.ledger.record("q2", 0.3)
        self.ledger.resolve(i2, 0)
        result = self.ledger.score()
        self.assertEqual(result["n"], 2)
        # brier = ((0.8-1)^2 + (0.3-0)^2) / 2 = (0.04 + 0.09) / 2 = 0.065
        self.assertAlmostEqual(result["brier"], 0.065)
        self.assertAlmostEqual(result["log_loss"],
                               -(math.log(0.8) + math.log(0.7)) / 2)

    def test_unresolved_forecasts_excluded_from_score(self):
        i1 = self.ledger.record("q1", 0.8)
        self.ledger.resolve(i1, 1)
        self.ledger.record("q2", 0.5)  # left unresolved
        result = self.ledger.score()
        self.assertEqual(result["n"], 1)

    def test_score_with_no_resolved_forecasts_returns_zero_n(self):
        self.ledger.record("q1", 0.5)  # unresolved
        result = self.ledger.score()
        self.assertEqual(result["n"], 0)

    def test_resolved_rows_carry_prediction_metadata_and_outcome(self):
        i1 = self.ledger.record("q1", 0.42, metric="ending_cash",
                                config_hash="abc123")
        self.ledger.resolve(i1, 1)
        rows = self.ledger.resolved()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["predicted_prob"], 0.42)
        self.assertEqual(rows[0]["outcome"], 1)
        self.assertEqual(rows[0]["metric"], "ending_cash")
        self.assertEqual(rows[0]["config_hash"], "abc123")

    def test_persists_across_connections(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "ledger.db")
        led = calibration.CalibrationLedger(path)
        fid = led.record("durable?", 0.6)
        led.resolve(fid, 1)
        # Re-open the same file in a fresh ledger instance
        reopened = calibration.CalibrationLedger(path)
        self.assertEqual(reopened.score()["n"], 1)


class TestReliabilityCurve(unittest.TestCase):
    def _ledger(self, pairs):
        led = calibration.CalibrationLedger(":memory:")
        for p, o in pairs:
            led.resolve(led.record("q", p), o)
        return led

    def test_two_extreme_bins(self):
        led = self._ledger([(0.05, 0), (0.05, 0), (0.95, 1), (0.95, 1)])
        curve = led.reliability_curve()
        self.assertEqual(len(curve), 2)
        lo, hi = curve[0], curve[1]
        self.assertEqual((lo["lo"], lo["hi"], lo["count"]), (0.0, 0.1, 2))
        self.assertAlmostEqual(lo["mean_predicted"], 0.05)
        self.assertAlmostEqual(lo["observed_freq"], 0.0)
        self.assertEqual((hi["lo"], hi["hi"], hi["count"]), (0.9, 1.0, 2))
        self.assertAlmostEqual(hi["observed_freq"], 1.0)

    def test_prob_one_lands_in_last_bin(self):
        curve = self._ledger([(1.0, 1)]).reliability_curve()
        self.assertEqual(len(curve), 1)
        self.assertEqual(curve[0]["lo"], 0.9)

    def test_exact_bin_boundaries_not_misbinned_by_float_error(self):
        # 0.3/0.1 == 2.9999... in float; naive int() would mis-bin 0.3 into [0.2,0.3).
        led = self._ledger([(0.3, 1), (0.7, 0), (0.9, 1)])
        los = {b["lo"] for b in led.reliability_curve()}
        self.assertEqual(los, {0.3, 0.7, 0.9})

    def test_empty_when_nothing_resolved(self):
        self.assertEqual(calibration.CalibrationLedger(":memory:").reliability_curve(), [])


class TestECE(unittest.TestCase):
    def _ledger(self, pairs):
        led = calibration.CalibrationLedger(":memory:")
        for p, o in pairs:
            led.resolve(led.record("q", p), o)
        return led

    def test_perfect_calibration_is_zero(self):
        led = self._ledger([(0.0, 0), (1.0, 1)])
        self.assertEqual(led.expected_calibration_error(), 0.0)

    def test_known_value(self):
        # bin0: pred 0.05 obs 0.0 -> |0.05|; bin9: pred 0.95 obs 1.0 -> |0.05|
        led = self._ledger([(0.05, 0), (0.05, 0), (0.95, 1), (0.95, 1)])
        self.assertAlmostEqual(led.expected_calibration_error(), 0.05)

    def test_none_when_empty(self):
        self.assertIsNone(calibration.CalibrationLedger(":memory:").expected_calibration_error())


class TestCalibrationReport(unittest.TestCase):
    def _ledger(self, pairs):
        led = calibration.CalibrationLedger(":memory:")
        for p, o in pairs:
            led.resolve(led.record("q", p), o)
        return led

    def test_empty(self):
        rep = calibration.CalibrationLedger(":memory:").calibration_report()
        self.assertEqual(rep["n"], 0)
        self.assertFalse(rep["ready"])
        self.assertIsNone(rep["curve"])
        self.assertIsNone(rep["ece"])
        self.assertEqual(rep["min_n"], calibration.MIN_RESOLVED_FOR_CURVE)

    def test_below_threshold_not_ready(self):
        rep = self._ledger([(0.5, 1), (0.5, 0)]).calibration_report()
        self.assertEqual(rep["n"], 2)
        self.assertFalse(rep["ready"])
        self.assertIsNone(rep["curve"])
        self.assertIsNotNone(rep["brier"])          # aggregate score still computed
        self.assertAlmostEqual(rep["base_rate"], 0.5)

    def test_at_threshold_ready_with_curve(self):
        rep = self._ledger([(0.9, 1)] * 10).calibration_report()
        self.assertEqual(rep["n"], 10)
        self.assertTrue(rep["ready"])
        self.assertTrue(rep["curve"])               # non-empty list
        self.assertIsNotNone(rep["ece"])


if __name__ == "__main__":
    unittest.main()

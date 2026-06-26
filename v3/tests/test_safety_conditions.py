#!/usr/bin/env python3
"""Chance-constraint condition-keyword handling.

Regression for the `lt`-inversion bug: the evaluator recognized only the literal
"below"/"above"; every synonym (lt, <, less_than, under, ...) silently fell
through to the greater-than branch, inverting the violation probability (a
near-all-positive profit metric reported P(loss)=100% instead of ~0%).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import kernel


def _eval(vals, condition, threshold, max_prob=0.5):
    raw = {"m": list(vals)}
    cfg = {"chance_constraints": [
        {"metric": "m", "condition": condition, "threshold": threshold, "max_prob": max_prob}
    ]}
    res = kernel._evaluate_safety_python(raw, cfg)
    return res["chance"][0]


class TestConditionAliases(unittest.TestCase):
    BELOW_ALIASES = ["below", "lt", "<", "less_than", "under", "lte", "<="]
    ABOVE_ALIASES = ["above", "gt", ">", "greater_than", "exceeds", "gte", ">="]

    def test_below_family_counts_less_than(self):
        vals = [-5, -1, 1, 2, 3]  # 2 of 5 are < 0
        for cond in self.BELOW_ALIASES:
            c = _eval(vals, cond, 0)
            self.assertAlmostEqual(
                c["actual_prob"], 0.4, msg=f"{cond!r} should count v < threshold")

    def test_above_family_counts_greater_than(self):
        vals = [-5, -1, 1, 2, 3]  # 3 of 5 are > 0
        for cond in self.ABOVE_ALIASES:
            c = _eval(vals, cond, 0)
            self.assertAlmostEqual(
                c["actual_prob"], 0.6, msg=f"{cond!r} should count v > threshold")

    def test_lt_on_all_positive_is_zero_not_one(self):
        # The exact reported inversion: profit always positive -> P(loss) ~ 0, PASS.
        c = _eval([100, 200, 300, 400], "lt", 0)
        self.assertEqual(c["actual_prob"], 0.0)
        self.assertTrue(c["passed"])

    def test_case_and_whitespace_insensitive(self):
        # Use a NEW alias under odd casing/spacing so this pins the fix (the old
        # code only ever recognized the bare literal "below").
        c = _eval([-1, 1], "  Lt  ", 0)
        self.assertAlmostEqual(c["actual_prob"], 0.5)

    def test_unknown_condition_raises(self):
        with self.assertRaises(ValueError):
            _eval([1, 2, 3], "sideways", 0)


if __name__ == "__main__":
    unittest.main()

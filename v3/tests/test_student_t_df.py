#!/usr/bin/env python3
"""Regression: student_t must accept non-integer df (it drives range())."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import kernel


class TestStudentTFractionalDf(unittest.TestCase):
    def test_fractional_df_samples_instead_of_raising(self):
        random.seed(0)
        for _ in range(50):
            v = kernel.SAMPLERS["student_t"]({"mean": 100, "scale": 20, "df": 4.5})
            self.assertTrue(isinstance(v, float))

    def test_df_below_one_clamped(self):
        random.seed(0)
        v = kernel.SAMPLERS["student_t"]({"df": 0.2})
        self.assertTrue(isinstance(v, float))

    def test_integer_df_unchanged(self):
        random.seed(7)
        a = kernel.SAMPLERS["student_t"]({"mean": 0, "scale": 1, "df": 5})
        self.assertTrue(isinstance(a, float))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Tests for static expression-name validation (validation.check_expression_names),
which catches references to undefined names/functions that the kernel would
otherwise silently evaluate to 0. Also guards every shipped domain against
false positives.
"""

import os
import sys
import json
import glob
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import validation

VALID = {
    "name": "Candles",
    "n_simulations": 100,
    "n_steps": 12,
    "parameters": {"monthly_sales": {"distribution": "triangular", "params": {"low": 20, "mode": 40, "high": 80}}},
    "controls": {"price": {"distribution": "fixed", "params": {"value": 15}}},
    "initial_state": {"cash": 0},
    "step_logic": [
        {"target": "revenue", "expr": "monthly_sales * price"},
        {"target": "profit", "expr": "revenue - 360"},
    ],
    "accumulators": {"cash": "cash + profit"},
    "metrics": {"final_cash": {"expr": "cash", "format": "dollar"}},
}


def with_expr(target_expr=None, metric_expr=None, accum_expr=None):
    cfg = json.loads(json.dumps(VALID))
    if target_expr is not None:
        cfg["step_logic"][1]["expr"] = target_expr
    if metric_expr is not None:
        cfg["metrics"]["final_cash"]["expr"] = metric_expr
    if accum_expr is not None:
        cfg["accumulators"]["cash"] = accum_expr
    return cfg


class TestExpressionNames(unittest.TestCase):
    def test_valid_config_has_no_name_errors(self):
        self.assertEqual(validation.check_expression_names(VALID), [])

    def test_flags_undefined_name_inf(self):
        errs = validation.check_expression_names(with_expr(target_expr="clamp(revenue - 360, 0, inf)"))
        self.assertTrue(any("inf" in e for e in errs))

    def test_flags_undefined_name_n_steps(self):
        errs = validation.check_expression_names(with_expr(metric_expr="cash / n_steps"))
        self.assertTrue(any("n_steps" in e for e in errs))

    def test_flags_lambda_and_filter(self):
        errs = validation.check_expression_names(
            with_expr(metric_expr="len(filter(lambda x: x < 0, profit))"))
        self.assertTrue(any("lambda" in e for e in errs) or any("filter" in e for e in errs))

    def test_flags_dotted_name(self):
        errs = validation.check_expression_names(with_expr(metric_expr="initial_state.cash"))
        self.assertTrue(any("dotted" in e.lower() or "initial_state" in e for e in errs))

    def test_allowed_functions_are_fine(self):
        errs = validation.check_expression_names(with_expr(target_expr="clamp(round(revenue), 0, 100000)"))
        self.assertEqual(errs, [])

    def test_validate_config_surfaces_name_errors(self):
        errors = validation.validate_config(with_expr(target_expr="clamp(revenue, 0, inf)"))
        self.assertTrue(any("inf" in e for e in errors))

    def test_all_shipped_domains_validate_clean(self):
        domains_dir = os.path.join(os.path.dirname(__file__), "..", "domains")
        files = [f for f in glob.glob(os.path.join(domains_dir, "*.json"))
                 if not os.path.basename(f).startswith("_")]
        self.assertTrue(files, "expected shipped domain configs")
        for f in files:
            with open(f) as fh:
                data = json.load(fh)
            name_errors = validation.check_expression_names(data)
            self.assertEqual(name_errors, [], f"{os.path.basename(f)} flagged: {name_errors}")


if __name__ == "__main__":
    unittest.main()

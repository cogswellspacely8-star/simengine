#!/usr/bin/env python3
"""
The validator must never crash on a malformed config — it should return clean,
human-readable errors. (Real bug: bare scalars/strings where dicts were expected
leaked '<int> object has no attribute get' tracebacks and masked later errors.)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import validation


class TestValidatorRobustness(unittest.TestCase):
    def test_scalar_parameter_does_not_crash(self):
        cfg = {
            "name": "x", "n_steps": 5,
            "parameters": {"win_target": 4},  # bare scalar, not a {distribution,...} dict
            "step_logic": [{"target": "y", "expr": "win_target"}],
            "metrics": {"y": {"expr": "y"}},
        }
        errors = validation.validate_config(cfg)  # must NOT raise
        self.assertTrue(any("win_target" in e for e in errors))
        self.assertTrue(any("object" in e.lower() or "int" in e.lower() for e in errors))

    def test_string_step_logic_does_not_crash(self):
        cfg = {
            "name": "x", "n_steps": 5,
            "parameters": {"p": {"distribution": "fixed", "params": {"value": 1}}},
            "step_logic": ["do the thing"],  # bare string, not a dict
            "metrics": {"y": {"expr": "p"}},
        }
        errors = validation.validate_config(cfg)  # must NOT raise
        self.assertTrue(any("step_logic" in e for e in errors))

    def test_step_logic_not_a_list(self):
        cfg = {
            "name": "x", "n_steps": 5,
            "parameters": {"p": {"distribution": "fixed", "params": {"value": 1}}},
            "step_logic": "oops",
            "metrics": {"y": {"expr": "p"}},
        }
        errors = validation.validate_config(cfg)
        self.assertTrue(any("step_logic" in e for e in errors))

    def test_arbitrary_garbage_returns_list_never_raises(self):
        for junk in [
            {"name": 5, "n_steps": "x", "parameters": [1, 2, 3]},
            {"parameters": {"a": ["not", "a", "dict"]}, "step_logic": [42]},
            {"metrics": "nope"},
        ]:
            errors = validation.validate_config(junk)
            self.assertIsInstance(errors, list)


def _valid_base():
    """A minimal, fully valid config to mutate per-test."""
    return {
        "name": "x", "n_steps": 3,
        "parameters": {"rate": {"distribution": "fixed", "params": {"value": 0.3}}},
        "step_logic": [{"target": "y", "expr": "rate * 10"}],
        "metrics": {"y": {"expr": "y"}},
    }


class TestOptimizerBlockValidation(unittest.TestCase):
    """tunable / fitness / safety blocks are consumed only by evolve(); a
    malformed shape used to pass /api/validate then crash evolve with an opaque
    500 ('str' object has no attribute 'get'). Catch them at design time."""

    def test_fully_valid_optimizer_config_has_no_errors(self):
        cfg = _valid_base()
        cfg["tunable"] = [{"path": "parameters.rate.params.value", "range": [0.1, 0.5]}]
        cfg["fitness"] = {"components": [{"expr": "y_median", "weight": 1.0}]}
        cfg["safety"] = {"chance_constraints": [
            {"metric": "y", "condition": "below", "threshold": 0, "max_prob": 0.2}]}
        self.assertEqual(validation.validate_config(cfg), [])

    def test_tunable_array_of_strings_rejected(self):
        cfg = _valid_base()
        cfg["tunable"] = ["parameters.rate.params.value"]
        errors = validation.validate_config(cfg)
        self.assertTrue(any("tunable" in e for e in errors), errors)
        self.assertTrue(any("path" in e or "range" in e for e in errors), errors)

    def test_tunable_missing_range_rejected(self):
        cfg = _valid_base()
        cfg["tunable"] = [{"path": "parameters.rate.params.value"}]
        errors = validation.validate_config(cfg)
        self.assertTrue(any("range" in e for e in errors), errors)

    def test_tunable_bad_range_rejected(self):
        cfg = _valid_base()
        cfg["tunable"] = [{"path": "parameters.rate.params.value", "range": [5, 1]}]
        errors = validation.validate_config(cfg)
        self.assertTrue(any("range" in e for e in errors), errors)

    def test_fitness_adhoc_weighted_keys_rejected(self):
        cfg = _valid_base()
        cfg["fitness"] = {"revenue": 0.5, "safety": 0.5}
        errors = validation.validate_config(cfg)
        self.assertTrue(any("components" in e for e in errors), errors)

    def test_fitness_component_missing_expr_rejected(self):
        cfg = _valid_base()
        cfg["fitness"] = {"components": [{"weight": 1.0}]}
        errors = validation.validate_config(cfg)
        self.assertTrue(any("expr" in e for e in errors), errors)

    def test_safety_unknown_condition_rejected(self):
        cfg = _valid_base()
        cfg["safety"] = {"chance_constraints": [
            {"metric": "y", "condition": "sideways", "threshold": 0, "max_prob": 0.2}]}
        errors = validation.validate_config(cfg)
        self.assertTrue(any("condition" in e for e in errors), errors)

    def test_safety_lt_alias_accepted(self):
        cfg = _valid_base()
        cfg["safety"] = {"chance_constraints": [
            {"metric": "y", "condition": "lt", "threshold": 0, "max_prob": 0.2}]}
        self.assertEqual(validation.validate_config(cfg), [])

    # --- never-raises on non-list constraint containers (the B1 crash) ---
    def test_chance_constraints_non_list_does_not_crash(self):
        cfg = _valid_base()
        cfg["safety"] = {"chance_constraints": 5}  # truthy non-list
        errs = validation.validate_config(cfg)     # must NOT raise
        self.assertIsInstance(errs, list)
        self.assertTrue(any("chance_constraints" in e for e in errs), errs)

    def test_cvar_constraints_non_list_does_not_crash(self):
        cfg = _valid_base()
        cfg["safety"] = {"cvar_constraints": 1.5}
        self.assertIsInstance(validation.validate_config(cfg), list)

    # --- close the opaque-500 hole: required fields + path resolution ---
    def test_tunable_path_must_resolve(self):
        cfg = _valid_base()
        cfg["tunable"] = [{"path": "controls.nonexistent.params.value", "range": [0, 1]}]
        errs = validation.validate_config(cfg)
        self.assertTrue(any("path" in e and ("resolve" in e or "nonexistent" in e) for e in errs), errs)

    def test_chance_constraint_missing_required_fields(self):
        cfg = _valid_base()
        cfg["safety"] = {"chance_constraints": [{"condition": "below"}]}
        errs = validation.validate_config(cfg)
        self.assertTrue(any("metric" in e for e in errs), errs)

    def test_cvar_constraint_missing_required_fields(self):
        cfg = _valid_base()
        cfg["safety"] = {"cvar_constraints": [{"metric": "y"}]}
        errs = validation.validate_config(cfg)
        self.assertTrue(any("alpha" in e or "min_cvar" in e for e in errs), errs)

    # --- NaN range and bad step ---
    def test_nan_range_rejected(self):
        cfg = _valid_base()
        cfg["tunable"] = [{"path": "parameters.rate.params.value", "range": [float("nan"), 1.0]}]
        errs = validation.validate_config(cfg)
        self.assertTrue(any("range" in e for e in errs), errs)

    def test_step_must_fit_in_range(self):
        cfg = _valid_base()
        cfg["tunable"] = [{"path": "parameters.rate.params.value", "range": [0, 1], "step": 5}]
        errs = validation.validate_config(cfg)
        self.assertTrue(any("step" in e for e in errs), errs)


class TestOptimizerBlockNeverRaises(unittest.TestCase):
    """The validator must return a list for ANY malformed optimizer block,
    because llm/compiler.py calls validate_config with no try/except."""

    def test_malformed_optimizer_blocks_never_raise(self):
        cases = {
            "tunable": [5, "x", {}, {"path": 1}, {"path": "a", "range": "x"},
                        {"path": "a", "range": [1]}, [1, 2], None, True],
            "fitness": [5, "x", {"components": 5}, {"components": [5]},
                        {"components": [{"weight": 1}]}, {"foo": "bar"}, None],
            "safety": [5, "x", {"chance_constraints": 5}, {"chance_constraints": [5]},
                       {"cvar_constraints": 7}, {"chance_constraints": [{"condition": True}]}, None],
        }
        for block, vals in cases.items():
            for v in vals:
                cfg = _valid_base()
                cfg[block] = v
                self.assertIsInstance(
                    validation.validate_config(cfg), list,
                    f"{block}={v!r} should return a list, not raise")


if __name__ == "__main__":
    unittest.main()

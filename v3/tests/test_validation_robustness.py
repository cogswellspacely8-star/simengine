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


if __name__ == "__main__":
    unittest.main()

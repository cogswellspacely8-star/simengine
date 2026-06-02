#!/usr/bin/env python3
"""
Contract test: the published JSON Schema must accept every shipped domain and
reject malformed configs. Uses the `jsonschema` library if available; skips
cleanly if not installed (the engine itself never depends on it).
"""

import os
import sys
import json
import glob
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

V3 = os.path.join(os.path.dirname(__file__), "..")
SCHEMA_PATH = os.path.join(V3, "schema", "domain.schema.json")
DOMAINS = [f for f in glob.glob(os.path.join(V3, "domains", "*.json"))
           if not os.path.basename(f).startswith("_")]


def _load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


class TestSchemaFileExists(unittest.TestCase):
    def test_schema_parses_and_has_required(self):
        s = _load_schema()  # always runs, no dep
        self.assertEqual(set(s["required"]), {"name", "n_steps", "step_logic", "metrics"})


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed (contract check skipped)")
class TestSchemaContract(unittest.TestCase):
    def setUp(self):
        self.schema = _load_schema()
        jsonschema.Draft202012Validator.check_schema(self.schema)
        self.validator = jsonschema.Draft202012Validator(self.schema)

    def test_accepts_every_shipped_domain(self):
        self.assertTrue(DOMAINS, "expected shipped domains")
        for f in DOMAINS:
            with open(f) as fh:
                data = json.load(fh)
            errors = sorted(self.validator.iter_errors(data), key=lambda e: e.path)
            self.assertEqual(errors, [], f"{os.path.basename(f)} rejected by schema: "
                                          f"{[e.message for e in errors]}")

    def test_rejects_bare_scalar_parameter(self):
        bad = {"name": "x", "n_steps": 5, "parameters": {"p": 0.5},
               "step_logic": [{"target": "y", "expr": "p"}], "metrics": {"y": {"expr": "y"}}}
        self.assertTrue(list(self.validator.iter_errors(bad)))

    def test_rejects_missing_metrics(self):
        bad = {"name": "x", "n_steps": 5,
               "parameters": {"p": {"distribution": "fixed", "params": {"value": 1}}},
               "step_logic": [{"target": "y", "expr": "p"}]}
        self.assertTrue(list(self.validator.iter_errors(bad)))

    def test_rejects_no_variable_category(self):
        bad = {"name": "x", "n_steps": 5,
               "step_logic": [{"target": "y", "expr": "1"}], "metrics": {"y": {"expr": "y"}}}
        self.assertTrue(list(self.validator.iter_errors(bad)))


if __name__ == "__main__":
    unittest.main()

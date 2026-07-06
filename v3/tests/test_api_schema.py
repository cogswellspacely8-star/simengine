#!/usr/bin/env python3
"""Tests for GET /api/schema (server.handle_schema) — the published config contract."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server


class TestApiSchema(unittest.TestCase):
    def test_serves_valid_json_schema(self):
        payload, status = server.handle_schema()
        self.assertEqual(status, 200)
        self.assertTrue(str(payload.get("$schema", "")).startswith("https://json-schema.org"))
        self.assertIn("properties", payload)
        # top-level required fields the engine enforces
        self.assertEqual(set(payload.get("required", [])), {"name", "n_steps", "step_logic", "metrics"})

    def test_schema_describes_the_distributions(self):
        payload, _ = server.handle_schema()
        text = str(payload)
        for dist in ["triangular", "bernoulli", "lognormal", "student_t"]:
            self.assertIn(dist, text)

    def test_condition_enum_matches_kernel_aliases(self):
        """The published contract must accept exactly what the kernel accepts."""
        import kernel
        payload, _ = server.handle_schema()
        defs = payload.get("$defs") or payload.get("definitions") or {}
        enum = set(defs["ChanceConstraint"]["properties"]["condition"]["enum"])
        self.assertEqual(enum,
                         set(kernel.BELOW_CONDITIONS) | set(kernel.ABOVE_CONDITIONS))


if __name__ == "__main__":
    unittest.main()

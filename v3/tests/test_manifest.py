#!/usr/bin/env python3
"""Tests for make_manifest's canonical config_hash (kernel.py).

The hash must identify the model, not its formatting: reformatting a config
file or reordering its keys must not change config_hash, while any change to a
value must. Zero external deps — stdlib unittest only.
"""

import json
import os
import sys
import tempfile
import unittest

# Make v3 package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kernel import make_manifest


class TestManifestHash(unittest.TestCase):
    def test_hash_has_expected_shape(self):
        m = make_manifest({"name": "x", "n_simulations": 100}, 100, 42)
        self.assertRegex(m["config_hash"], r"^[0-9a-f]{16}$")
        self.assertEqual(m["n_simulations"], 100)
        self.assertEqual(m["seed"], 42)

    def test_hash_ignores_key_order(self):
        a = {"name": "m", "n_simulations": 5000, "seed": 42}
        b = {"seed": 42, "n_simulations": 5000, "name": "m"}  # reordered
        self.assertEqual(
            make_manifest(a, 5000, 42)["config_hash"],
            make_manifest(b, 5000, 42)["config_hash"],
        )

    def test_hash_matches_between_reformatted_file_and_dict(self):
        cfg = {"name": "m", "parameters": {"p": {"distribution": "fixed", "params": {"value": 1}}}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            # pretty-printed AND key-reordered on disk — must still hash identically
            json.dump({"parameters": cfg["parameters"], "name": cfg["name"]}, f, indent=4)
            path = f.name
        try:
            self.assertEqual(
                make_manifest(cfg, 100, 1)["config_hash"],
                make_manifest(path, 100, 1)["config_hash"],
            )
        finally:
            os.unlink(path)

    def test_hash_changes_when_a_value_changes(self):
        a = {"name": "m", "parameters": {"p": {"distribution": "fixed", "params": {"value": 1}}}}
        b = json.loads(json.dumps(a))
        b["parameters"]["p"]["params"]["value"] = 2
        self.assertNotEqual(
            make_manifest(a, 100, 1)["config_hash"],
            make_manifest(b, 100, 1)["config_hash"],
        )

    def test_non_ascii_name_hashes_consistently(self):
        # em dash in a name must not break hashing (ensure_ascii=False, UTF-8)
        m = make_manifest({"name": "Indie SaaS — MRR"}, 100, 1)
        self.assertRegex(m["config_hash"], r"^[0-9a-f]{16}$")


if __name__ == "__main__":
    unittest.main()

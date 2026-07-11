#!/usr/bin/env python3
"""Packaging invariants for the simengine-mcp PyPI distribution.

(a) v3/__init__.py carries a sys.path bootstrap needed only by the installed
    package (see its docstring). In-repo, every module uses flat absolute
    imports (`from kernel import ...`), so nothing should ever import the
    `v3` package itself — that must stay true or the bootstrap becomes live
    and could mask real in-repo import bugs.
(b) The published version must be identical across pyproject.toml,
    v3/__init__.py, and server.json — a release with mismatched versions is
    a broken release.

Stdlib only.
"""

import ast
import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

EXCLUDED_DIR_NAMES = {
    ".git", ".venv", "dist", "build", ".superpowers", "target", "node_modules",
}

IMPORT_V3_RE = re.compile(r"^\s*(import\s+v3\b|from\s+v3\s+import\b)", re.MULTILINE)


def _iter_repo_files():
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
        for name in filenames:
            yield os.path.join(dirpath, name)


class TestNoInRepoImportOfV3Package(unittest.TestCase):
    """The v3/__init__.py sys.path bootstrap must stay inert in-repo."""

    def test_no_file_imports_v3_package(self):
        offenders = []
        for path in _iter_repo_files():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            if IMPORT_V3_RE.search(text):
                offenders.append(os.path.relpath(path, REPO_ROOT))
        self.assertEqual(
            offenders, [],
            "Found 'import v3' / 'from v3 import' in-repo — this would make "
            "the sys.path bootstrap in v3/__init__.py live outside the "
            "installed-package case: %s" % offenders,
        )


class TestVersionLockstep(unittest.TestCase):
    """pyproject.toml, v3/__init__.py, and server.json must agree on version."""

    def _pyproject_version(self):
        path = os.path.join(REPO_ROOT, "pyproject.toml")
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match, "no version= found in pyproject.toml")
        return match.group(1)

    def _init_version(self):
        path = os.path.join(REPO_ROOT, "v3", "__init__.py")
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__version__":
                        value = node.value
                        if isinstance(value, ast.Constant):
                            return value.value
        self.fail("no __version__ found in v3/__init__.py")

    def _server_json_version(self):
        import json
        path = os.path.join(REPO_ROOT, "server.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("version", data, "no top-level version in server.json")
        return data["version"]

    def test_versions_match_across_all_three_files(self):
        pyproject_version = self._pyproject_version()
        init_version = self._init_version()
        server_json_version = self._server_json_version()
        self.assertEqual(
            (pyproject_version, init_version, server_json_version),
            (pyproject_version, pyproject_version, pyproject_version),
            "version mismatch: pyproject.toml=%r v3/__init__.py=%r server.json=%r"
            % (pyproject_version, init_version, server_json_version),
        )


if __name__ == "__main__":
    unittest.main()

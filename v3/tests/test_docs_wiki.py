#!/usr/bin/env python3
"""
Tests for the docs wiki (docs/README.md hub) and its MCP exposure (docs_wiki.py,
list_docs / search_docs / read_doc tools, simengine:// resources).

Wiki hygiene is enforced here: every page under docs/ must be listed on the
hub, and every relative link in the docs must resolve.
Uses only Python stdlib unittest — zero external dependencies.
"""

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import docs_wiki
import mcp_server

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")


def _md_files(root):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.endswith(".md"):
                yield os.path.join(dirpath, name)


def _repo_rel(path):
    return os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")


class _DefaultDocsDir(unittest.TestCase):
    """Run with the in-repo docs/ regardless of the caller's environment."""

    def setUp(self):
        self._saved = os.environ.pop("SIMENGINE_DOCS_DIR", None)

    def tearDown(self):
        os.environ.pop("SIMENGINE_DOCS_DIR", None)
        if self._saved is not None:
            os.environ["SIMENGINE_DOCS_DIR"] = self._saved


class TestWikiHygiene(_DefaultDocsDir):

    def test_every_doc_is_listed_on_the_hub(self):
        listed = {e["id"] for e in docs_wiki.catalog()}
        orphans = sorted(_repo_rel(p) for p in _md_files(DOCS_DIR)
                         if _repo_rel(p) not in listed)
        self.assertEqual(orphans, [],
                         "Add these pages to docs/README.md so they are indexed "
                         "and reachable over MCP: %s" % orphans)

    def test_every_hub_entry_exists(self):
        with open(os.path.join(DOCS_DIR, "README.md"), encoding="utf-8") as f:
            entries = docs_wiki.parse_hub(f.read())
        self.assertGreater(len(entries), 20)
        missing = [e["id"] for e in entries
                   if not os.path.isfile(os.path.join(REPO_ROOT, e["id"]))]
        self.assertEqual(missing, [])

    def test_hub_entries_have_summaries(self):
        blank = [e["id"] for e in docs_wiki.catalog() if not e["summary"]]
        self.assertEqual(blank, [])

    def test_relative_links_resolve(self):
        broken = []
        for path in _md_files(DOCS_DIR):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for target in LINK_RE.findall(text):
                target = target.split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
                if not os.path.exists(resolved):
                    broken.append("%s -> %s" % (_repo_rel(path), target))
        self.assertEqual(broken, [])


class TestDocsWikiModule(_DefaultDocsDir):

    def test_list_docs_sections(self):
        out = docs_wiki.list_docs()
        self.assertEqual(out["sections"][:3], ["home", "guide", "reference"])
        ids = [d["id"] for d in out["docs"]]
        self.assertIn("docs/schema-reference.md", ids)
        self.assertIn("v3/AGENT_INTEGRATION.md", ids)
        self.assertNotIn("note", out)

    def test_list_docs_section_filter(self):
        out = docs_wiki.list_docs(section="Evidence")
        self.assertEqual([d["section"] for d in out["docs"]], ["evidence"])

    def test_read_doc_accepts_id_uri_and_short_path(self):
        for ref in ("docs/feeds.md", "simengine://docs/feeds.md", "feeds.md", "feeds"):
            out = docs_wiki.read_doc(ref)
            self.assertEqual(out.get("id"), "docs/feeds.md", ref)
            self.assertIn("Polymarket", out["content"])

    def test_read_doc_heading_section(self):
        out = docs_wiki.read_doc("docs/schema-reference.md", heading="safety")
        self.assertTrue(out["content"].startswith("## Safety"))
        self.assertIn("cvar_constraints", out["content"])
        self.assertNotIn("## Fitness", out["content"])

    def test_read_doc_unknown_heading_lists_headings(self):
        out = docs_wiki.read_doc("docs/decision-gate.md", heading="no such heading")
        self.assertIn("error", out)
        self.assertIn("The problem it solves", out["headings"])
        self.assertNotIn("content", out)

    def test_read_doc_rejects_paths_outside_catalog(self):
        for ref in ("../v3/kernel.py", "docs/../v3/kernel.py", "v3/kernel.py",
                    "/etc/passwd", "simengine://docs/../../etc/passwd", "", None):
            self.assertIn("error", docs_wiki.read_doc(ref), ref)

    def test_search_ranks_and_snippets(self):
        out = docs_wiki.search_docs("cvar_constraints")
        self.assertEqual(out["match"], "all")
        self.assertEqual(out["results"][0]["id"], "docs/schema-reference.md")
        self.assertTrue(out["results"][0]["snippets"][0]["line"] > 0)

    def test_search_falls_back_to_any_term(self):
        out = docs_wiki.search_docs("polymarket zzzznotaword")
        self.assertEqual(out["match"], "any")
        self.assertIn("docs/feeds.md", [r["id"] for r in out["results"]])

    def test_search_empty_query(self):
        self.assertIn("error", docs_wiki.search_docs("   "))

    def test_extract_section_ignores_headings_in_code_fences(self):
        text = "# T\n## A\n```\n# not a heading\n```\nbody\n## B\nb\n"
        self.assertEqual(docs_wiki.extract_section(text, "A"),
                         "## A\n```\n# not a heading\n```\nbody\n")

    def test_resources_round_trip(self):
        resources = docs_wiki.list_resources()
        self.assertEqual(len(resources), len(docs_wiki.catalog()))
        first = resources[0]
        self.assertEqual(first["uri"], "simengine://docs/README.md")
        content = docs_wiki.read_resource(first["uri"])
        self.assertEqual(content["mimeType"], "text/markdown")
        self.assertIn("# SimEngine Wiki", content["text"])
        self.assertIsNone(docs_wiki.read_resource("simengine://docs/../v3/kernel.py"))
        self.assertIsNone(docs_wiki.read_resource("file:///etc/passwd"))


class TestWheelFallback(_DefaultDocsDir):
    """Without docs/ (wheel installs), only the bundled agent guide is served."""

    def test_bundled_docs_only(self):
        with tempfile.TemporaryDirectory() as empty:
            os.environ["SIMENGINE_DOCS_DIR"] = empty
            out = docs_wiki.list_docs()
            self.assertEqual([d["id"] for d in out["docs"]], ["v3/AGENT_INTEGRATION.md"])
            self.assertIn("SIMENGINE_DOCS_DIR", out["note"])
            self.assertIn("content", docs_wiki.read_doc("v3/AGENT_INTEGRATION.md"))
            self.assertIn("error", docs_wiki.read_doc("docs/feeds.md"))

    def test_override_points_at_other_docs_dir(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
                f.write("# Hub\n\n## Notes\n\n- [Hello](hello.md) — a page\n")
            with open(os.path.join(d, "hello.md"), "w", encoding="utf-8") as f:
                f.write("# Hello\n\nworld\n")
            os.environ["SIMENGINE_DOCS_DIR"] = d
            ids = [e["id"] for e in docs_wiki.catalog()]
            self.assertEqual(ids, ["docs/README.md", "docs/hello.md"])
            self.assertIn("world", docs_wiki.read_doc("hello")["content"])


class TestMcpExposure(_DefaultDocsDir):

    def test_tools_registered(self):
        names = [t["name"] for t in mcp_server.TOOLS]
        for name in ("list_docs", "search_docs", "read_doc"):
            self.assertIn(name, names)
            self.assertIn(name, mcp_server.HANDLERS)

    def test_handlers_are_json_serializable(self):
        for name, args in (("list_docs", {}),
                           ("search_docs", {"query": "decision gate", "limit": 2}),
                           ("read_doc", {"id": "docs/README.md"})):
            out = mcp_server.HANDLERS[name](args)
            self.assertNotIn("error", out, name)
            json.dumps(out)

    def test_server_version_matches_package(self):
        with open(os.path.join(REPO_ROOT, "pyproject.toml"), encoding="utf-8") as f:
            m = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.MULTILINE)
        self.assertEqual(mcp_server._server_version(), m.group(1))


if __name__ == "__main__":
    unittest.main()

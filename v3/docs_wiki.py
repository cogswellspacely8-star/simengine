"""
SimEngine docs wiki — index, search, and read the project docs for MCP clients.
===============================================================================
The catalog is the hub page `docs/README.md`: every `- [Title](path) — summary`
bullet under a `## Section` heading is one entry. Keeping the hub as the single
source of truth means the human-facing index and the MCP-facing index can't
drift (`tests/test_docs_wiki.py` also fails on orphan pages and broken links).

Doc ids are repo-relative paths (`docs/guide/02-quickstart.md`,
`v3/AGENT_INTEGRATION.md`) so they match the links in the README. Only ids in
the catalog can be read — there is no arbitrary file access.

In-repo, `docs/` sits next to `v3/`. The PyPI wheel ships only `v3/`, so there
the catalog falls back to the agent docs bundled inside the package. Point
`SIMENGINE_DOCS_DIR` at a checkout's `docs/` to serve the full wiki anyway.

Stdlib only.
"""

import os
import re

V3_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_FILE = "README.md"
URI_PREFIX = "simengine://"
REPO_DOCS_URL = "https://github.com/cogswellspacely8-star/simengine/tree/main/docs"

# Docs that ship inside v3/ (and therefore the wheel); served even without docs/.
BUNDLED_DOCS = [
    {
        "id": "v3/AGENT_INTEGRATION.md",
        "section": "reference",
        "summary": "How an AI agent builds, validates, runs, and interprets a simulation over HTTP",
    },
]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ENTRY_RE = re.compile(r"^\s*[-*]\s+\[([^\]]+)\]\(([^)\s#]+)(?:#[^)]*)?\)\s*(.*)$")
_SUMMARY_LEAD_RE = re.compile(r"^(?:—|–|-|:)\s*")


def docs_dir():
    """The wiki's docs/ directory, or None when it isn't available (e.g. wheel installs)."""
    override = os.environ.get("SIMENGINE_DOCS_DIR")
    candidates = [override] if override else [os.path.join(V3_DIR, "..", "docs")]
    for cand in candidates:
        if cand and os.path.isfile(os.path.join(cand, HUB_FILE)):
            return os.path.abspath(cand)
    return None


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _id_to_path(doc_id, ddir):
    """Map a repo-relative id to a file on disk (None if outside docs/ and v3/)."""
    parts = doc_id.split("/", 1)
    if len(parts) != 2:
        return None
    root, rest = parts
    if root == "docs" and ddir:
        return os.path.join(ddir, rest)
    if root == "v3":
        return os.path.join(V3_DIR, rest)
    return None


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _title_of(text, fallback):
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) == 1:
            return m.group(2)
    return fallback


def parse_hub(text):
    """Parse hub markdown into [{id, title, section, summary}] in document order.

    Only the first link of each bullet is an entry; later links in the same
    bullet (e.g. a results JSON) are supporting material, not wiki pages.
    """
    entries = []
    section = None
    for line in text.splitlines():
        h = _HEADING_RE.match(line)
        if h:
            if len(h.group(1)) == 2:
                section = _slug(h.group(2))
            continue
        m = _ENTRY_RE.match(line)
        if not m or section is None:
            continue
        title, target, rest = m.group(1), m.group(2), m.group(3)
        if "://" in target or not target.endswith(".md"):
            continue
        doc_id = os.path.normpath(os.path.join("docs", target)).replace(os.sep, "/")
        summary = _SUMMARY_LEAD_RE.sub("", rest).strip()
        entries.append({"id": doc_id, "title": title, "section": section, "summary": summary})
    return entries


def catalog():
    """All servable docs: [{id, title, section, summary, uri, path}]."""
    ddir = docs_dir()
    entries = []
    if ddir:
        hub_id = "docs/" + HUB_FILE
        entries.append({
            "id": hub_id, "title": "SimEngine Wiki", "section": "home",
            "summary": "Wiki home: what every page is for and where it lives",
        })
        entries.extend(parse_hub(_read(os.path.join(ddir, HUB_FILE))))
    else:
        for b in BUNDLED_DOCS:
            path = _id_to_path(b["id"], None)
            if path and os.path.isfile(path):
                entry = dict(b)
                entry["title"] = _title_of(_read(path), b["id"])
                entries.append(entry)

    seen = set()
    out = []
    for e in entries:
        path = _id_to_path(e["id"], ddir)
        if e["id"] in seen or not path or not os.path.isfile(path):
            continue
        seen.add(e["id"])
        e = dict(e, uri=URI_PREFIX + e["id"], path=path)
        out.append(e)
    return out


def _public(entry):
    return {k: entry[k] for k in ("id", "title", "section", "summary", "uri")}


def _resolve(catalog_entries, ref):
    """Find a catalog entry by id, URI, or docs-relative path ('guide/02-quickstart.md')."""
    if not isinstance(ref, str) or not ref.strip():
        return None
    ref = ref.strip()
    if ref.startswith(URI_PREFIX):
        ref = ref[len(URI_PREFIX):]
    ref = ref.lstrip("/")
    by_id = {e["id"]: e for e in catalog_entries}
    for cand in (ref, "docs/" + ref, ref + ".md", "docs/" + ref + ".md"):
        if cand in by_id:
            return by_id[cand]
    return None


def _not_available_note():
    return ("The full docs wiki is not bundled with this install. Set SIMENGINE_DOCS_DIR "
            "to a SimEngine checkout's docs/ directory, or browse " + REPO_DOCS_URL)


def list_docs(section=None):
    entries = catalog()
    sections = []
    for e in entries:
        if e["section"] not in sections:
            sections.append(e["section"])
    if section:
        wanted = _slug(section)
        entries = [e for e in entries if e["section"] == wanted]
    result = {"sections": sections, "docs": [_public(e) for e in entries]}
    if docs_dir() is None:
        result["note"] = _not_available_note()
    return result


def outline(text):
    """Markdown headings as [{level, title}] — skips fenced code blocks."""
    out = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m:
            out.append({"level": len(m.group(1)), "title": m.group(2)})
    return out


def extract_section(text, heading):
    """Return the text under `heading` (case-insensitive) up to the next heading of
    the same or higher level, or None if there is no such heading."""
    want = heading.strip().lstrip("#").strip().lower()
    lines = text.splitlines()
    start = level = None
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        lvl = len(m.group(1))
        if start is None:
            if m.group(2).lower() == want:
                start, level = i, lvl
        elif lvl <= level:
            return "\n".join(lines[start:i]).rstrip() + "\n"
    if start is None:
        return None
    return "\n".join(lines[start:]).rstrip() + "\n"


def read_doc(doc_id, heading=None):
    entries = catalog()
    entry = _resolve(entries, doc_id)
    if entry is None:
        err = {"error": "Unknown doc %r. Call list_docs for valid ids." % (doc_id,)}
        if docs_dir() is None:
            err["note"] = _not_available_note()
        return err
    text = _read(entry["path"])
    result = _public(entry)
    if heading:
        part = extract_section(text, heading)
        if part is None:
            result["error"] = "No heading %r in %s." % (heading, entry["id"])
            result["headings"] = [h["title"] for h in outline(text)]
            return result
        result["heading"] = heading
        text = part
    result["content"] = text
    return result


def search_docs(query, limit=10, section=None):
    terms = [t for t in re.split(r"\s+", (query or "").lower()) if t]
    if not terms:
        return {"error": "Provide a non-empty query."}
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 10
    entries = catalog()
    if section:
        entries = [e for e in entries if e["section"] == _slug(section)]

    def score(e, text, mode):
        low = text.lower()
        title = e["title"].lower()
        hits = [low.count(t) + title.count(t) for t in terms]
        if mode == "all" and not all(hits):
            return 0
        return sum(hits) + 5 * sum(1 for t in terms if t in title)

    docs = [(e, _read(e["path"])) for e in entries]
    results = []
    match_mode = "all"
    for mode in ("all", "any"):
        scored = [(score(e, t, mode), e, t) for e, t in docs]
        scored = [s for s in scored if s[0] > 0]
        if scored:
            match_mode = mode
            break
    else:
        scored = []
    scored.sort(key=lambda s: (-s[0], s[1]["id"]))
    for s, e, text in scored[:limit]:
        snippets = []
        for n, line in enumerate(text.splitlines(), 1):
            if any(t in line.lower() for t in terms):
                snippets.append({"line": n, "text": line.strip()[:200]})
                if len(snippets) == 3:
                    break
        item = _public(e)
        item.update(score=s, snippets=snippets)
        results.append(item)
    out = {"query": query, "match": match_mode, "results": results}
    if docs_dir() is None:
        out["note"] = _not_available_note()
    return out


# ---------------------------------------------------------------------------
# MCP resources (resources/list, resources/read)
# ---------------------------------------------------------------------------

def list_resources():
    return [
        {
            "uri": e["uri"],
            "name": e["id"],
            "title": e["title"],
            "description": e["summary"],
            "mimeType": "text/markdown",
        }
        for e in catalog()
    ]


def read_resource(uri):
    """Return {uri, mimeType, text} for a simengine:// doc URI, or None if unknown."""
    if not isinstance(uri, str) or not uri.startswith(URI_PREFIX):
        return None
    entry = _resolve(catalog(), uri)
    if entry is None:
        return None
    return {"uri": entry["uri"], "mimeType": "text/markdown", "text": _read(entry["path"])}

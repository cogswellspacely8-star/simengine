# Hosted MCP Pipeline — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 0 of the hosted-MCP revenue pipeline: publishable `simengine-mcp` PyPI package, official MCP registry listing, a GitHub Pages landing page with waitlist, and the finalized demand-probe post — per the approved spec `docs/superpowers/specs/2026-07-11-hosted-mcp-revenue-pipeline-design.md`.

**Architecture:** Everything in this phase is free and channel-independent. Packaging wraps the existing `v3/` modules as a zero-dependency wheel (`package-dir` maps `v3/` → `simengine_mcp`); the registry listing points at that wheel; the landing page is one static HTML file in a new public repo (`simengine-site`) served by GitHub Pages; the probe text is finalized in the existing `docs/demand-probe.md`. Phases 1–2 get their own plans after the probe resolves.

**Tech Stack:** Python 3.8+ stdlib only (runtime); `build`/`twine` (dev-only); `mcp-publisher` CLI (Go binary, dev-only); plain HTML/CSS (no build step); Formspree free tier (waitlist form); GitHub Pages (free on public repos).

## Global Constraints

- Zero runtime Python dependencies in `v3/` — `dependencies = []` in packaging; `build`/`twine` are dev tooling only and must never appear as runtime deps.
- No frontend build step — the landing page is one hand-written HTML file.
- Version lockstep: `v3/__init__.py` `__version__`, `server.json` `version`, and `pyproject.toml` `version` are all `3.0.0` and must stay identical.
- GitHub costs stay at the $4/mo Pro flat rate: GitHub Pages only (free on public repos), **no** GitHub Actions workflows in either repo.
- Positioning guardrails (from `docs/server-card.md`): never claim "the only general decision-intelligence MCP server"; never imply async task handles, market-prediction skill, or financial advice; say "outcome risk," never "model confidence."
- Human-gated steps are marked **[TONY]** — they need credentials or an outward-facing action only Tony can authorize. Everything else is executable by the engineer.

---

### Task 1: MCP stdio smoke-test script

The test harness comes first so Tasks 2–3 have something to verify against. It speaks raw JSON-RPC over stdio to any MCP server command and asserts the SimEngine tool surface.

**Files:**
- Create: `scripts/smoke_mcp_stdio.py`

**Interfaces:**
- Produces: `python3 scripts/smoke_mcp_stdio.py <command...>` — exits 0 and prints `SMOKE OK (9 tools, N domains)` when the served tool list contains all 9 SimEngine tools and a `list_domains` call returns a non-empty result; exits 1 otherwise. Tasks 2 and 3 run it against `python3 v3/mcp_server.py` and `uvx simengine-mcp` respectively.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Smoke-test an MCP stdio server: initialize, list tools, call list_domains.

Usage: python3 scripts/smoke_mcp_stdio.py <server command...>
  e.g. python3 scripts/smoke_mcp_stdio.py python3 v3/mcp_server.py
       python3 scripts/smoke_mcp_stdio.py uvx simengine-mcp
Exits 0 on success, 1 on any failure. Stdlib only.
"""
import json
import subprocess
import sys

EXPECTED_TOOLS = {
    "simulate", "list_domains", "validate_config", "optimize",
    "update_bayesian", "convergence_check", "sensitivity_analysis",
    "baseline_comparison", "decide_under_uncertainty",
}
TIMEOUT = 60


def rpc(proc, req_id, method, params=None):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout before responding")
        line = line.strip()
        if not line:
            continue
        resp = json.loads(line)
        if resp.get("id") == req_id:
            if "error" in resp:
                raise RuntimeError("RPC error from %s: %s" % (method, resp["error"]))
            return resp["result"]


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    proc = subprocess.Popen(
        argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        rpc(proc, 1, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "0"},
        })
        proc.stdin.write(
            (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
        proc.stdin.flush()
        tools = {t["name"] for t in rpc(proc, 2, "tools/list")["tools"]}
        missing = EXPECTED_TOOLS - tools
        if missing:
            print("SMOKE FAIL: missing tools: %s" % sorted(missing), file=sys.stderr)
            return 1
        result = rpc(proc, 3, "tools/call", {"name": "list_domains", "arguments": {}})
        text = json.dumps(result)
        payload = json.loads(result["content"][0]["text"])
        domains = payload.get("domains", payload if isinstance(payload, list) else [])
        if not domains:
            print("SMOKE FAIL: list_domains returned no domains: %s" % text[:200],
                  file=sys.stderr)
            return 1
        print("SMOKE OK (%d tools, %d domains)" % (len(tools), len(domains)))
        return 0
    finally:
        proc.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Run it against the in-repo server to verify it passes**

Run: `cd ~/projects/simengine && timeout 60 python3 scripts/smoke_mcp_stdio.py python3 v3/mcp_server.py`
Expected: `SMOKE OK (9 tools, N domains)` with N ≥ 14, exit 0.
If the `domains` payload shape assertion fails, inspect the actual `list_domains` response (`python3 -c` one-liner or add a debug print) and adjust the `payload` extraction to match the server's real response shape — the assertion that matters is *non-empty domains list*.

- [ ] **Step 3: Run it against a broken command to verify it fails**

Run: `timeout 60 python3 scripts/smoke_mcp_stdio.py python3 -c "pass"; echo "exit=$?"`
Expected: `SMOKE FAIL`/`RuntimeError` output and `exit=1`.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_mcp_stdio.py
git commit -m "test(mcp): stdio smoke script for packaged and in-repo MCP server"
```

---

### Task 2: PyPI packaging (`pyproject.toml`, `README-pypi.md`, `main()` entry point)

Implements steps 1–3 of `docs/PUBLISHING-MCP-REGISTRY.md`. The wheel must be zero-dependency and carry the domain JSON files so `list_domains` works when installed.

**Files:**
- Create: `pyproject.toml` (repo root)
- Create: `README-pypi.md` (repo root)
- Modify: `v3/mcp_server.py:635-641` (wrap entry point in `main()`)
- Test: `scripts/smoke_mcp_stdio.py` (from Task 1) against the installed wheel in a fresh venv

**Interfaces:**
- Consumes: `scripts/smoke_mcp_stdio.py <command...>` from Task 1.
- Produces: installable `simengine-mcp` wheel exposing console script `simengine-mcp` → `simengine_mcp.mcp_server:main`; `main()` function in `v3/mcp_server.py`. Task 3 uploads exactly this artifact.

- [ ] **Step 1: Add `main()` to `v3/mcp_server.py`**

Replace the current entry block (lines 635–641):

```python
if __name__ == "__main__":
    try:
        run_with_mcp_sdk()
    except ImportError:
        # MCP SDK not installed — fall back to raw JSON-RPC
        print("MCP SDK not found, using raw stdio JSON-RPC transport", file=sys.stderr)
        run_with_stdio_jsonrpc()
```

with:

```python
def main():
    """Console entry point (simengine-mcp). Same behaviour as running the module."""
    try:
        run_with_mcp_sdk()
    except ImportError:
        # MCP SDK not installed — fall back to raw JSON-RPC
        print("MCP SDK not found, using raw stdio JSON-RPC transport", file=sys.stderr)
        run_with_stdio_jsonrpc()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the in-repo server still works**

Run: `timeout 60 python3 scripts/smoke_mcp_stdio.py python3 v3/mcp_server.py && make test`
Expected: `SMOKE OK …` and the full unittest suite passing (286 tests, OK, some skipped).

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "simengine-mcp"
version = "3.0.0"
description = "Monte Carlo decision-intelligence over MCP — zero-dependency pure-Python engine"
readme = "README-pypi.md"
requires-python = ">=3.8"
license = { text = "Apache-2.0" }
authors = [{ name = "Venture Horizon LLC / OtrovertLabs" }]
keywords = ["mcp", "monte-carlo", "simulation", "decision-intelligence", "risk", "optimization"]
dependencies = []                     # ZERO — the pure-stdlib promise

[project.optional-dependencies]
sdk = ["mcp>=1.0"]                    # optional official-SDK path; stdlib JSON-RPC is the default

[project.scripts]
simengine-mcp = "simengine_mcp.mcp_server:main"

[project.urls]
Homepage = "https://github.com/cogswellspacely8-star/simengine"
Source = "https://github.com/cogswellspacely8-star/simengine"

[tool.setuptools]
package-dir = { "simengine_mcp" = "v3" }
packages = ["simengine_mcp"]

[tool.setuptools.package-data]
simengine_mcp = ["domains/*.json", "schema/*.json", "mcp_config.json"]
```

Note: `packages` is explicit (not `find`) so `v3/tests`, `v3/static`, `v3/feeds`, and `v3/llm` stay out of the wheel; `package-data` carries the JSON the tools need at runtime.

- [ ] **Step 4: Write `README-pypi.md`**

```markdown
mcp-name: io.github.cogswellspacely8-star/simengine

# simengine-mcp

Monte Carlo decision intelligence over MCP. Give your agent a real
outcome-distribution calculator: schema-contracted simulation, chance/CVaR
safety constraints, sensitivity analysis, and a proceed/escalate decision
gate (`decide_under_uncertainty`) — all pure Python stdlib, zero
dependencies.

## Run

    uvx simengine-mcp

or add it to any MCP client as a stdio server with command `simengine-mcp`.

## Tools (9)

`simulate`, `validate_config`, `list_domains`, `optimize`,
`update_bayesian`, `convergence_check`, `sensitivity_analysis`,
`baseline_comparison`, `decide_under_uncertainty`.

## Validated

Backtested on 2,819 walk-forward monthly forecasts over up to seven decades
of public FRED data, scored with proper scoring rules (Brier, log loss,
ECE). Details, source, docs, and the full engine (web UI, HTTP API):
https://github.com/cogswellspacely8-star/simengine

It models **outcome risk** — the spread of results given uncertain inputs —
as decision support. It is not financial advice and issues no trade signals.

License: Apache-2.0 (engine). A hosted service is offered separately under a
commercial license.
```

Before Task 3 uploads, verify the `mcp-name:` marker syntax against the current
quickstart at https://modelcontextprotocol.io/registry/quickstart (the format
has moved before; as of 2026-07 it is a plain `mcp-name: <name>` line near the
top of the package README).

- [ ] **Step 5: Build the wheel**

Run:
```bash
cd ~/projects/simengine
python3 -m pip install --user --upgrade build twine   # dev tooling only
python3 -m build
ls dist/
```
Expected: `dist/simengine_mcp-3.0.0-py3-none-any.whl` and the sdist, no errors.

- [ ] **Step 6: Install into a fresh venv and smoke-test the console script**

Run:
```bash
python3 -m venv /tmp/se-pkg-test
/tmp/se-pkg-test/bin/pip install --no-deps dist/simengine_mcp-3.0.0-py3-none-any.whl
timeout 60 python3 scripts/smoke_mcp_stdio.py /tmp/se-pkg-test/bin/simengine-mcp
```
Expected: `SMOKE OK (9 tools, N domains)` with N ≥ 14 — proving the console
script resolves, the stdlib JSON-RPC fallback engages (no `mcp` SDK in the
venv), and domain JSON shipped in the wheel.

- [ ] **Step 7: Verify the wheel is dependency-free**

Run: `/tmp/se-pkg-test/bin/pip freeze | grep -v simengine-mcp | wc -l`
Expected: `0` (nothing but the package itself).

- [ ] **Step 8: Check the wheel doesn't leak tests or the UI**

Run: `python3 -m zipfile -l dist/simengine_mcp-3.0.0-py3-none-any.whl | grep -cE "tests/|static/|feeds/|llm/"`
Expected: `0`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml README-pypi.md v3/mcp_server.py
git commit -m "feat(packaging): zero-dep simengine-mcp wheel with console entry point"
```

---

### Task 3: Publish to PyPI **[TONY: PyPI account + API token]**

Decision gate 1 from the runbook — reserving the public `simengine-mcp` name. Approved by the Phase 0 spec.

**Files:**
- No repo changes; publishes `dist/*` from Task 2.

**Interfaces:**
- Consumes: `dist/simengine_mcp-3.0.0*` from Task 2.
- Produces: `simengine-mcp==3.0.0` live on PyPI, runnable via `uvx simengine-mcp`. Task 4's registry listing points at it.

- [ ] **Step 1 [TONY]: Create/confirm PyPI account and project-scoped API token** at https://pypi.org/manage/account/token/

- [ ] **Step 2: Upload**

Run:
```bash
cd ~/projects/simengine
TWINE_USERNAME=__token__ TWINE_PASSWORD="<paste token>" python3 -m twine upload dist/*
```
Expected: `View at https://pypi.org/project/simengine-mcp/3.0.0/` — do not echo the token into shell history files; prefer twine's interactive prompt if unsure.

- [ ] **Step 3: Smoke-test the published package from a clean environment**

Run: `timeout 120 python3 scripts/smoke_mcp_stdio.py uvx simengine-mcp`
Expected: `SMOKE OK (9 tools, N domains)`. (First run downloads the wheel; allow the longer timeout.)

- [ ] **Step 4: Confirm zero transitive dependencies from PyPI's view**

Run: `python3 -m pip download simengine-mcp --no-deps -d /tmp/se-dl && ls /tmp/se-dl | wc -l`
Expected: `1` — exactly one artifact.

---

### Task 4: Publish the MCP registry listing **[TONY: GitHub device-flow login]**

Decision gate 2 from the runbook. `server.json` already exists at the repo root, pinned to 3.0.0.

**Files:**
- No repo changes expected; `server.json` is already correct. If `mcp-publisher` validation demands schema updates, edit `server.json` minimally and commit.

**Interfaces:**
- Consumes: `server.json` (repo root); the live PyPI package from Task 3; the `mcp-name:` marker in the PyPI README from Task 2.
- Produces: public listing `io.github.cogswellspacely8-star/simengine` on `registry.modelcontextprotocol.io`. The landing page (Task 5) links to it.

- [ ] **Step 1: Install the publisher CLI**

Run:
```bash
cd /tmp/claude-1000/-home-tony-projects-simengine/*/scratchpad 2>/dev/null || cd /tmp
curl -sSL https://raw.githubusercontent.com/modelcontextprotocol/registry/main/scripts/install.sh | sh
mcp-publisher --version
```
Expected: a version string. (Go binary; install location per the script's output — add to PATH if needed.)

- [ ] **Step 2 [TONY]: Authenticate**

Run: `cd ~/projects/simengine && mcp-publisher login github`
Expected: GitHub device-flow prompt; Tony completes it in the browser, authorizing the `io.github.cogswellspacely8-star/*` namespace.

- [ ] **Step 3: Publish**

Run: `cd ~/projects/simengine && mcp-publisher publish`
Expected: validation passes and the CLI reports the listing created. If validation rejects `server.json`, fix the reported field, commit the fix (`git add server.json && git commit -m "fix(mcp): registry schema compliance"`), and re-run.

- [ ] **Step 4: Verify the listing resolves**

Run: `curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=simengine" | python3 -m json.tool | head -40`
Expected: one entry named `io.github.cogswellspacely8-star/simengine` pointing at PyPI package `simengine-mcp` version `3.0.0`.

- [ ] **Step 5 [TONY, optional but recommended]: Add via a real client**

In Claude Code or Claude Desktop, add the server from the registry entry and confirm all 9 tools appear and `list_domains` runs.

- [ ] **Step 6: Mark the runbook done**

Edit `docs/PUBLISHING-MCP-REGISTRY.md`: change the intro line "the two **decision gates** below are yours to trigger" to note both gates were triggered on 2026-07-11 per the Phase 0 spec, with the PyPI and registry URLs. Commit:

```bash
git add docs/PUBLISHING-MCP-REGISTRY.md
git commit -m "docs(mcp): registry + PyPI published; runbook marked executed"
```

---

### Task 5: Landing page — `simengine-site` repo + GitHub Pages **[TONY: Formspree form ID]**

One static HTML file, no build step. This repo later hosts the Phase 2 track-record page, so it's separate from the engine repo by design.

**Files:**
- Create (new repo `~/projects/simengine-site/`): `index.html`, `README.md`
- Test: local `python3 -m http.server` + curl assertions, then the live Pages URL

**Interfaces:**
- Consumes: registry listing URL (Task 4), `uvx simengine-mcp` (Task 3), backtest numbers from `docs/backtests/2026-07-06-fred-monthly-calibration.md`, copy from `docs/server-card.md`.
- Produces: live page at `https://cogswellspacely8-star.github.io/simengine-site/` with a working waitlist form. Phase 2's flywheel will commit `track-record.html` into this same repo.

- [ ] **Step 1 [TONY]: Create a Formspree form** (free tier, ~5 min) at https://formspree.io — one form named "SimEngine hosted waitlist"; note the form endpoint `https://formspree.io/f/<FORM_ID>`.

- [ ] **Step 2: Create the repo**

Run:
```bash
mkdir -p ~/projects/simengine-site && cd ~/projects/simengine-site
git init -b main
gh repo create cogswellspacely8-star/simengine-site --public --source=. --description "SimEngine — Monte Carlo decision intelligence for AI agents (landing + live track record)"
```
Expected: repo created and remote wired.

- [ ] **Step 3: Write `index.html`** (replace `FORM_ID` with the real Formspree ID from Step 1):

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SimEngine — Monte Carlo decision intelligence for AI agents</title>
<meta name="description" content="Give your agent a real outcome-distribution calculator: validated, schema-contracted Monte Carlo simulation with a proceed/escalate decision gate, over MCP.">
<style>
  :root { --fg:#1a1a1a; --bg:#fdfdfc; --accent:#0b5cad; --muted:#666; --line:#e3e1dc; }
  @media (prefers-color-scheme: dark) {
    :root { --fg:#e8e6e3; --bg:#141414; --accent:#6db3f2; --muted:#9a9a9a; --line:#2c2c2c; }
  }
  * { box-sizing: border-box; }
  body { margin:0; font:17px/1.6 system-ui, sans-serif; color:var(--fg); background:var(--bg); }
  main { max-width: 720px; margin: 0 auto; padding: 3rem 1.25rem 4rem; }
  h1 { font-size: 2rem; line-height:1.2; margin: 0 0 .5rem; }
  h2 { font-size: 1.25rem; margin: 2.5rem 0 .75rem; }
  .sub { color: var(--muted); font-size: 1.05rem; margin: 0 0 2rem; }
  pre { background: rgba(127,127,127,.12); padding: .75rem 1rem; border-radius: 6px; overflow-x:auto; }
  code { font-family: ui-monospace, monospace; font-size: .95em; }
  table { border-collapse: collapse; width: 100%; font-size: .92rem; }
  th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--line); }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .note { color: var(--muted); font-size: .9rem; }
  form { display:flex; gap:.5rem; flex-wrap:wrap; margin:.75rem 0; }
  input[type=email] { flex:1 1 220px; padding:.6rem .8rem; font-size:1rem; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); }
  button { padding:.6rem 1.2rem; font-size:1rem; border:0; border-radius:6px; background:var(--accent); color:#fff; cursor:pointer; }
  a { color: var(--accent); }
  footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--line); font-size:.85rem; color:var(--muted); }
</style>
</head>
<body>
<main>
  <h1>Stop your agent from acting on overconfident guesses.</h1>
  <p class="sub">SimEngine gives an AI agent a real outcome-distribution calculator:
  schema-contracted Monte Carlo simulation, chance/CVaR safety constraints, and a
  <strong>proceed / escalate</strong> decision gate — over MCP, pure Python stdlib,
  zero dependencies.</p>

  <h2>Run it now</h2>
  <pre><code>uvx simengine-mcp</code></pre>
  <p>Or find it on the <a href="https://registry.modelcontextprotocol.io/?search=simengine">official MCP registry</a>,
  or <a href="https://github.com/cogswellspacely8-star/simengine">clone the engine</a> —
  web UI, HTTP API, and CLI included. Python 3.8+ is the only requirement.</p>

  <h2>Why trust the numbers</h2>
  <p>The forecast pipeline is backtested on <strong>2,819 walk-forward monthly
  forecasts</strong> over up to seven decades of public FRED data — every one produced
  through the real engine path and scored with proper scoring rules
  (<a href="https://github.com/cogswellspacely8-star/simengine/blob/main/docs/backtests/2026-07-06-fred-monthly-calibration.md">full report</a>):</p>
  <table>
    <tr><th>Task</th><th class="num">n</th><th class="num">Brier</th><th class="num">ECE</th></tr>
    <tr><td>CPI inflation &gt; 0.25% MoM</td><td class="num">831</td><td class="num">0.2317</td><td class="num">0.081</td></tr>
    <tr><td>Industrial production falls</td><td class="num">1,168</td><td class="num">0.2379</td><td class="num">0.060</td></tr>
    <tr><td>Unemployment rate rises</td><td class="num">820</td><td class="num">0.2515</td><td class="num">0.171</td></tr>
  </table>
  <p class="note">This validates that engine-produced probabilities are
  <em>calibrated</em>, not that they beat markets. SimEngine models outcome risk —
  the spread of results given uncertain inputs — as decision support. It is not
  financial advice and issues no trade signals.</p>

  <h2>The decision gate</h2>
  <p>An agent hands <code>decide_under_uncertainty</code> a quick model of a decision
  and the outcome range it can live with. The engine runs thousands of futures and
  answers: <em>“82% of simulated outcomes keep cash above zero — that clears your 80%
  bar, proceed”</em> — or <em>escalate</em>, with the tail risk spelled out.
  Nine tools total: simulate, validate, optimize, Bayesian update, sensitivity,
  convergence, baseline comparison, domain listing, and the gate.</p>

  <h2 id="waitlist">Hosted endpoint — join the waitlist</h2>
  <p>A managed, agent-ready HTTPS endpoint is coming: no install, instant API key,
  free tier. Leave an email and you'll get an invite when it opens.</p>
  <form action="https://formspree.io/f/FORM_ID" method="POST">
    <input type="email" name="email" required placeholder="you@company.com" aria-label="Email">
    <button type="submit">Join the waitlist</button>
  </form>
  <p class="note">One email when the hosted tier opens. Nothing else.</p>

  <footer>
    Engine: Apache-2.0, <a href="https://github.com/cogswellspacely8-star/simengine">open source</a>.
    Hosted service: commercial (Venture Horizon LLC / OtrovertLabs).
  </footer>
</main>
</body>
</html>
```

- [ ] **Step 4: Write `README.md`**

```markdown
# simengine-site

Landing page + (soon) live forecast track record for
[SimEngine](https://github.com/cogswellspacely8-star/simengine).
Static HTML, no build step, served by GitHub Pages.
```

- [ ] **Step 5: Test locally**

Run:
```bash
cd ~/projects/simengine-site && python3 -m http.server 8899 &
sleep 1
curl -s http://localhost:8899/ | grep -c "formspree.io/f/FORM_ID"   # must be 0 — ID was substituted
curl -s http://localhost:8899/ | grep -cE "decide_under_uncertainty|2,819|uvx simengine-mcp"
kill %1
```
Expected: first grep `0` (placeholder replaced), second grep `3`. Also open `http://localhost:8899` in a browser and confirm layout in both light and dark scheme.

- [ ] **Step 6: Push and enable Pages**

Run:
```bash
cd ~/projects/simengine-site
git add index.html README.md
git commit -m "feat: landing page with backtest trust anchor and hosted waitlist"
git push -u origin main
gh api -X POST repos/cogswellspacely8-star/simengine-site/pages -f build_type=workflow 2>/dev/null \
  || gh api -X POST repos/cogswellspacely8-star/simengine-site/pages -f "source[branch]=main" -f "source[path]=/"
```
Expected: Pages enabled from `main` branch root (the second form is the correct one for branch-based builds; the first is a guard against API shape drift — if both fail, enable Pages in the repo Settings UI, source = `main` / root).

- [ ] **Step 7: Verify live**

Run: `sleep 90 && curl -s https://cogswellspacely8-star.github.io/simengine-site/ | grep -c "decide_under_uncertainty"`
Expected: `1` (or more). Then submit the waitlist form once with a test address and confirm Formspree records it.

- [ ] **Step 8: Cross-link from the engine repo**

In `~/projects/simengine`, edit `README.md`: in the install/quickstart area add

```markdown
## Install as an MCP server

    uvx simengine-mcp

Listed on the [official MCP registry](https://registry.modelcontextprotocol.io/?search=simengine).
Hosted, no-install endpoint: [join the waitlist](https://cogswellspacely8-star.github.io/simengine-site/#waitlist).
```

and add the same two links to `llms.txt`. Commit:

```bash
cd ~/projects/simengine
git add README.md llms.txt
git commit -m "docs: uvx install, registry listing, and hosted-waitlist links"
```

---

### Task 6: Finalize the demand probe **[TONY: posting]**

The draft in `docs/demand-probe.md` is already good; this task pins the final text, channels, and a response log so the 48-hour decision rule gets applied to recorded evidence, not memory.

**Files:**
- Modify: `docs/demand-probe.md`

**Interfaces:**
- Consumes: the existing draft post and decision-rule table in `docs/demand-probe.md`.
- Produces: a `## FINAL — posted text and log` section; the Phase 1 plan reads the outcome tier from this file.

- [ ] **Step 1: Append the final section to `docs/demand-probe.md`**

```markdown
## FINAL — posted text and log (2026-07-11)

Post text: the draft above, verbatim, with one addition at the end:
"(It's open source and runs with zero deps — `uvx simengine-mcp` — but I'm
asking about the idea, not driving installs.)"

Channels (pick both):
1. r/AI_Agents — as a "would you use this" question
2. Anthropic developer community MCP channel

Rules: post the same day in both; no other links; reply to every response;
do not post the landing page unless someone asks where to find it.

### Response log

| # | Channel | Response (quote/summary) | Signal (use / pay / no) | Timestamp |
|---|---------|--------------------------|--------------------------|-----------|
| 1 | | | | |

### Outcome (fill at +48h)

- Organic "I'd use this / send a link" count: __
- Tier per decision rule above: **10+ / 3–9 / ≤2** → __
- Phase 1 consequence: full build / free-tier-only build / stop
```

- [ ] **Step 2: Commit**

```bash
git add docs/demand-probe.md
git commit -m "docs(probe): final post text, channels, and 48h response log"
```

- [ ] **Step 3 [TONY]: Post in both channels and start the 48-hour clock.** Log responses in the table as they arrive.

- [ ] **Step 4 (at +48h): Record the outcome tier in the file and commit** — this is the input gate for the Phase 1 plan.

```bash
git add docs/demand-probe.md
git commit -m "docs(probe): 48h outcome recorded — tier <X>"
```

---

## After Phase 0

- Probe tier **10+**: write the Phase 1 plan (full: `simengine-cloud` private repo, `gateway.py` Streamable HTTP MCP, keys + caps, Stripe Payment Links + webhook + reconcile, VPS + Caddy + systemd, security-and-hardening gate).
- Probe tier **3–9**: write the Phase 1 plan scoped to the free hosted tier only (keys, caps, instrumentation; no Stripe).
- Probe tier **≤2**: stop; landing page + registry listing remain as credibility assets; effort returns to consulting.
- Phase 2 (flywheel) plan is written once Phase 1 is live in either form.

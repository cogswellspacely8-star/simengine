# Publishing SimEngine to the official MCP registry

Runbook for listing SimEngine on `registry.modelcontextprotocol.io` as the
decision-intelligence MCP server. This is the highest-consensus GTM move in the
wiki (distribution through the channel AI clients actually read). Everything
here is prepared; the two **decision gates** below are yours to trigger.

## The one hard fact that shapes everything

**The registry stores metadata only — not code.** It will not host or run the
server; it points clients at a package they install themselves. So a listing
requires the server to be published to a supported package registry **first**.
Supported: `pypi`, `npm`, `nuget`, `oci` (Docker), `mcpb` (MCP bundle).

For a Python stdio server, that means **PyPI**. Which collides, on its face,
with SimEngine's "zero pip install" brand.

## Why the brand tension actually dissolves

The promise is "the engine needs **no third-party dependencies**," not "never
installable." `v3/mcp_server.py` already proves it: it tries the optional `mcp`
SDK and **falls back to hand-rolled stdlib JSON-RPC** ([mcp_server.py:635](../v3/mcp_server.py#L635)),
and every module under `v3/` imports only the standard library. So we can ship a
**genuinely zero-dependency** `simengine-mcp` wheel. `uvx simengine-mcp` then
pulls a package with no transitive deps — the purest possible expression of the
tagline, not a violation of it. (This is backlog item #9, "PyPI packaging,"
which was gated on exactly this question. The answer is: it's consistent.)

## Decision gate 1 — reserve `simengine-mcp` on PyPI?

`simengine` is already taken (an unrelated HA-systems tool). **`simengine-mcp`
is available** (verified 404 on PyPI). Publishing reserves that public name
under your account. Reversible only by yanking versions, not by freeing the name.

## Decision gate 2 — publish the registry listing?

`mcp-publisher publish` creates a public listing under
`io.github.cogswellspacely8-star/*`. Reversible (you can delete/deprecate), but
it's an outward-facing announcement. Do it when the README + package are how you
want them seen.

---

## Step-by-step (once gate 1 is a yes)

### 1. Add packaging (`pyproject.toml` at repo root)

The flat `v3/*.py` modules install cleanly as a package because
`mcp_server.py` inserts its own directory onto `sys.path`
([mcp_server.py:36](../v3/mcp_server.py#L36)) — so the flat `from kernel import …`
imports keep resolving even when installed as `simengine_mcp`.

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
dependencies = []                     # ZERO — the pure-stdlib promise, enforced by CI

[project.optional-dependencies]
sdk = ["mcp>=1.0"]                     # optional official-SDK path; stdlib JSON-RPC is the default

[project.scripts]
simengine-mcp = "simengine_mcp.mcp_server:main"

[project.urls]
Homepage = "https://github.com/cogswellspacely8-star/simengine"
Source = "https://github.com/cogswellspacely8-star/simengine"

[tool.setuptools]
package-dir = { "simengine_mcp" = "v3" }

[tool.setuptools.packages.find]
where = ["v3"]
```

### 2. Add a `main()` entry point

`v3/mcp_server.py` runs its logic inside `if __name__ == "__main__":`. Wrap it so
the console script can call it (a ~5-line, behaviour-preserving change):

```python
def main():
    """Console entry point (simengine-mcp). Same behaviour as running the module."""
    try:
        run_with_mcp_sdk()
    except ImportError:
        print("MCP SDK not found, using raw stdio JSON-RPC transport", file=sys.stderr)
        run_with_stdio_jsonrpc()

if __name__ == "__main__":
    main()
```

### 3. Add the ownership marker to the PyPI readme

The registry verifies you own the package by looking for a marker in the PyPI
long-description. Create `README-pypi.md` (kept short; the full README stays as
is) containing, near the top:

```
mcp-name: io.github.cogswellspacely8-star/simengine
```

> Verify the exact marker syntax against the current quickstart at
> https://modelcontextprotocol.io/registry/quickstart before publishing — the
> registry is young and the marker format has moved. As of writing it's an
> `mcp-name: <name>` line (or an equivalent HTML comment) in the package README.

### 4. Build and publish the package to PyPI

Build tooling (`build`, `twine`) are **dev-time only** — they never become
runtime dependencies, so the zero-dep promise holds.

```bash
cd ~/projects/simengine
python3 -m pip install --upgrade build twine     # dev tooling only
python3 -m build                                  # -> dist/simengine_mcp-3.0.0*
python3 -m twine upload dist/*                    # needs a PyPI account + API token
```

### 5. Smoke-test the published package BEFORE listing it

```bash
uvx simengine-mcp        # should start and speak MCP over stdio (Ctrl-C to exit)
```

Confirm the wheel is dependency-free:

```bash
python3 -m pip download simengine-mcp --no-deps -d /tmp/se && ls /tmp/se
# exactly one artifact, no dependency wheels pulled
```

### 6. Publish the registry listing (decision gate 2)

```bash
# Install the publisher CLI (Go binary; see the quickstart for the current install line)
curl -sSL https://raw.githubusercontent.com/modelcontextprotocol/registry/main/scripts/install.sh | sh

mcp-publisher login github        # opens the GitHub device flow; authorizes the
                                  # io.github.cogswellspacely8-star/* namespace
mcp-publisher publish             # reads ./server.json, validates, submits
```

`server.json` is already written at the repo root and pinned to version 3.0.0.
Bump both its `version` and the package `version` in lockstep on every release.

## Verify

1. Search the registry for `simengine` (or GET
   `https://registry.modelcontextprotocol.io/v0/servers?search=simengine`) and
   confirm the listing resolves to the PyPI package.
2. In a fresh MCP client (Claude Desktop / Claude Code), add the server via the
   registry entry and confirm all 9 tools appear: `simulate`, `list_domains`,
   `validate_config`, `optimize`, `update_bayesian`, `convergence_check`,
   `sensitivity_analysis`, `baseline_comparison`, `decide_under_uncertainty`.
3. Confirm the pure-Python path still works with the SDK absent
   (`pip uninstall mcp` in the test env → `uvx simengine-mcp` still serves).

## Keep in lockstep on every release

- `v3/__init__.py` `__version__`, `server.json` `version`, and the package
  `version` in `pyproject.toml` must match.
- Re-run `python3 -m build && twine upload` then `mcp-publisher publish`.

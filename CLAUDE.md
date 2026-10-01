# CLAUDE.md — SimEngine

## What this is

A domain-agnostic Monte Carlo simulation and decision intelligence system. Define variables, logic, and risk tolerances in JSON; the engine simulates thousands of futures and (optionally) evolves toward strategies that respect safety constraints. Used both as a standalone web UI and as an MCP/HTTP tool for AI agents.

**Open-core licensed.** The engine in this repo is Apache 2.0. The hosted MCP service is commercial (see `LICENSE-COMMERCIAL.md`). Don't conflate the two when modifying licenses or deployment guidance.

## Hard constraint: zero Python dependencies

The default engine uses **only the Python standard library.** This is a load-bearing design choice — it means SimEngine runs anywhere Python 3.8+ runs, no pip install required. **Do not add `requirements.txt` entries or `import` statements that pull external packages into `v3/*.py`.** If you think you need a third-party lib, you almost certainly don't — check `kernel.py` and `bayesian.py` for the pattern.

The Rust acceleration crates under `crates/` are the only exception, and they're explicitly **opt-in** — the Python code falls back gracefully when `simengine_native` isn't importable.

`v3/feeds/` (real-time data adapters like Polymarket Gamma) and `v3/llm/` (the natural-language front door) are also opt-in and network-touching, but stay inside the stdlib promise — they use only `urllib`. The core engine never imports them. Treat any new feed as opt-in and ToS-careful: market data is an **internal simulation input**, never a rebroadcast feed or trade signal. The `llm/` module turns a question into a config via a draft→validate→repair loop; the engine's own `validate_config` (in `validation.py`) grounds whatever the model produces.

## Stack

- **Engine:** Python 3.8+ stdlib (`v3/kernel.py`, `v3/bayesian.py`, `v3/diagnostics.py`, `v3/calibration.py`)
- **Web server:** Python stdlib `http.server` (`v3/server.py`, port 8420)
- **UI:** Single-page vanilla HTML/JS/CSS (`v3/static/index.html`) — no React, no framework, no build step
- **Native acceleration (optional):** Rust crates at `crates/simengine-core` and `crates/simengine-py` (PyO3), built with maturin
- **Tests:** Python `unittest` at `v3/tests/`
- **MCP server:** `v3/mcp_server.py` (config: `v3/mcp_config.json`)
- **Natural-language front door (optional):** `v3/llm/` + the `v3/sim_ask.py` CLI + the `/api/ask` endpoint + the web "Ask anything" tab. Local-first via Ollama; OpenAI/Anthropic via env var.

## Local dev

```bash
# Run the web UI (the canonical entry point)
cd v3 && python3 server.py
# -> http://localhost:8420

# Run tests
make test                # Python tests
make rust-test          # Rust crate tests

# Build native acceleration (one-time)
make native-install
make native-check       # confirm import works
make native-bench       # compare native vs pure-Python perf
```

`smoke_test.py` at the repo root is a quick sanity check.

## Layout

```
v3/                        ALL production code lives here
  kernel.py                Monte Carlo engine, distributions, optimizer, manifests
  server.py                HTTP server + all API endpoints
  bayesian.py              Conjugate prior updates
  diagnostics.py           Convergence, sensitivity, AST evaluator
  calibration.py           Proper scoring rules (Brier/log-loss/CRPS) + sqlite3 forecast ledger (wired to /api/forecast|resolve|forecasts + the Predictions UI)
  backtest.py              Historical calibration backtest: walk-forward FRED forecasts through the engine, scored via calibration.py (offline from backtest_data/; --fetch refreshes, opt-in network)
  backtest_data/           Committed FRED CSV snapshots (UNRATE/CPIAUCSL/INDPRO) so the backtest is reproducible offline
  validation.py            Canonical config validation (shared by server + llm compiler); never raises on bad shapes
  native.py                Optional Rust loader + Python fallback glue
  mcp_server.py            MCP tool exposure (12 tools incl. decide_under_uncertainty + list_docs/search_docs/read_doc) and docs resources
  docs_wiki.py             Docs wiki index/search/read for MCP; catalog = docs/README.md (orphan + link check in tests/test_docs_wiki.py)
  sim_ask.py               CLI: ask a plain-language question -> config -> run -> explain
  static/index.html        Vanilla SPA UI (one file) — incl. Ask-anything + Predictions modals
  domains/                 Example JSON configs (saas, real_estate, nba_finals_2026, btc, fed, etc.)
  schema/                  domain.schema.json — published JSON Schema, served at GET /api/schema
  feeds/                   OPT-IN real-time data adapters (Polymarket Gamma); stdlib urllib only
  llm/                     OPT-IN natural-language front door (backends, compiler, clarify, explain, ask); stdlib urllib only
  AGENT_INTEGRATION.md     HTTP agent guide (bundled in the wheel; served by read_doc)
  tests/                   unittest suites (200+; jsonschema contract test skips if lib absent)
docs/                      The docs wiki. README.md is the home/index — every page must be listed there (test-enforced)
crates/
  simengine-core/          Pure Rust numeric kernels
  simengine-py/            PyO3 bridge (module: simengine_native)
scripts/
  bench_native.py          Performance comparison
  install_native.sh        Native build helper
  smoke_mcp_stdio.py        MCP stdio smoke test (initialize, list tools, list_domains); wrap with shell `timeout`
Makefile                   Targets: venv, native-install, native-check, native-test, native-bench, test, rust-test
pyproject.toml              PyPI packaging (simengine-mcp); version must match v3/__init__.py and server.json
README-pypi.md              PyPI long description (separate from the repo README)
server.json                 MCP registry manifest; version must match pyproject.toml and v3/__init__.py
```

## Things to verify before claiming a change works

1. `make test` passes
2. If you touched a Rust crate: `make rust-test` and `make native-bench`
3. If you touched the kernel or distributions: run a known domain config (e.g. `v3/domains/business_pipeline_v3.json`) and confirm the histogram + risk gauge make sense
4. If you touched the API: hit `/api/health` and POST a config to `/api/simulate` with curl
5. If you touched the UI: open `http://localhost:8420` and exercise the affected feature
6. **Most important:** confirm the pure-Python path still works without the Rust extension. `SIMENGINE_DISABLE_NATIVE_SAMPLING=1 python3 v3/server.py` should produce identical results (within Monte Carlo noise) to the native path.

## Don't do

- Don't add a Python dependency to `v3/`. The pure-stdlib promise is the brand.
- Don't add a frontend build step. The UI is one HTML file by design.
- Don't make the Rust extension required. It must remain opt-in with graceful fallback.
- Don't change the default port (8420) without updating `mcp_config.json`, all docs, and any agent integrations that hardcoded it.
- Don't break the JSON config schema in `domains/_template.json` — domain configs are user-authored and a schema break is a usability regression.
- Don't move production code out of `v3/`. The README documents that location and external integrations may rely on it.

## Packaging / PyPI

`v3/` is also published as the zero-dependency PyPI package `simengine-mcp` (console script `simengine-mcp`, runnable via `uvx simengine-mcp` with no install step).

- **Version lockstep, enforced.** `version` in `pyproject.toml`, `__version__` in `v3/__init__.py`, and `version` in `server.json` must be identical. `v3/tests/test_packaging_invariants.py` fails the suite if they drift.
- **`v3/__init__.py` carries a sys.path bootstrap** needed only by the installed package (so its sibling flat imports like `from kernel import ...` still resolve under the `simengine_mcp` package name). It must stay inert in-repo — no `import v3` or `from v3 import` anywhere in the tree. Also test-enforced, same file.
- **Releasing:** follow `docs/PUBLISHING-MCP-REGISTRY.md`.

## Environment overrides (handy for benchmarking and triage)

- `SIMENGINE_DISABLE_NATIVE_SAMPLING=1` — force pure-Python sampling
- `SIMENGINE_DISABLE_NATIVE_EXPR_SAMPLING=1` — disable native binomial fast path
- `SIMENGINE_DISABLE_EXPR_CACHE=1` — disable parsed-expression cache
- `SIMENGINE_DISABLE_SAFE_EXPR_CACHE=1` — disable diagnostics AST cache
- `SIMENGINE_DOCS_DIR` — docs wiki directory served by the MCP doc tools (default: `docs/` next to `v3/`; wheel installs only bundle `v3/AGENT_INTEGRATION.md`)

### LLM front door (`v3/llm/`, `sim_ask.py`, `/api/ask`)

- `SIMENGINE_LLM_BACKEND` — `ollama` (default) | `openai` | `anthropic`
- `SIMENGINE_LLM_MODEL` — model name (default: a small instruct model, `qwen2.5`)
- `SIMENGINE_LLM_TIMEOUT` — per-request seconds (default 120; raise for slow local models)
- `OLLAMA_HOST` (default `http://localhost:11434`)
- `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1`; the base URL also covers llama.cpp / LM Studio / vLLM)
- `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`
- `SIMENGINE_OLLAMA_KEEP_ALIVE` (default `30m`; warm-start so the model isn't reloaded each call) and `SIMENGINE_OLLAMA_NUM_GPU` (force layer offload)
- `SIMENGINE_LEDGER_DB` (calibration ledger sqlite path; default `v3/forecasts.db`, gitignored)

Note: the server runs on `ThreadingHTTPServer` so a slow `/api/ask` never blocks the UI. If local LLM calls are slow, check that Ollama is actually using the GPU (`ollama ps` should not show 100% CPU) — a boot-race can leave it CPU-only until `systemctl restart ollama`.

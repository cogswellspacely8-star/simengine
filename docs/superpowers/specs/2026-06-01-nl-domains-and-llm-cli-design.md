# Natural-Language Domains & LLM CLI — Design

**Date:** 2026-06-01
**Status:** Approved (design); pending implementation plan
**Owner:** Tony / Venture Horizon LLC

## Summary

Let anyone use SimEngine for *any* question of uncertainty — not just the pre-built domains — by adding a natural-language front door. Two faces, one shared engine:

1. A web **"Ask anything"** tab: type a question, get an answer.
2. An **LLM CLI** (`sim_ask`): run the same loop from the terminal, designed to work with **small local models**.

Both share one pipeline:

```
question → LLM drafts a config → validate → repair loop (feed errors back) → run_monte_carlo → LLM explains the real stats
```

## Why this works with small models

The small model does not have to be *right* in one shot — it has to be *correctable*. The engine already ships `validate_config` (catches unknown distributions, missing fields, NaN-producing expressions) and 15 real domains + `_template.json` to use as few-shot examples. The compiler drafts → validates → feeds the exact errors back → re-drafts until valid, then runs real math. The engine grounds the model — the same "verify against reality" ethos as the calibration ledger. A 7B local model typically converges in 1–2 repair rounds.

## Goals

- Turn a plain-language question into a valid SimEngine domain config, run it, and explain the result in the user's own terms.
- Default to a **local** model (Ollama) — free, private, offline, no API key. API backends optional via env var.
- Keep the core engine zero-dependency. The new code is opt-in and stdlib-only.
- Reuse what exists: `validate_config`, `run_monte_carlo`, the deterministic narrative, the save-domain flow, the existing UI render and config editor.

## Non-goals

- No new third-party dependency in the core or anywhere in `v3/` (urllib only).
- Not a fine-tuned model or a hosted inference service (that can come later under the commercial MCP).
- Not replacing the existing guided wizard — the "Ask anything" tab sits alongside it.
- No streaming token UI in v1 (a simple "Thinking…" state is enough; streaming is a future nicety).

## Architecture

### New module: `v3/llm/` (opt-in, stdlib `urllib` only, core never imports it)

Analogous to `v3/feeds/`. Add a CLAUDE.md carve-out marking it opt-in and network-touching but inside the stdlib promise.

- **`backends.py`** — provider-agnostic chat: `complete(messages, *, model=None, temperature=0.0, json_mode=False) -> str`. Backend selected by `SIMENGINE_LLM_BACKEND` (default `ollama`):
  - **Ollama** — `POST {OLLAMA_HOST or http://localhost:11434}/api/chat`, uses Ollama's `format: "json"` when `json_mode`. Model from `SIMENGINE_LLM_MODEL` (default a small instruct model, e.g. `qwen2.5`).
  - **OpenAI-compatible** — `POST {OPENAI_BASE_URL or https://api.openai.com/v1}/chat/completions`, `Authorization: Bearer $OPENAI_API_KEY`. The configurable base URL also covers llama.cpp / LM Studio / vLLM OpenAI-compatible servers for free.
  - **Anthropic** — `POST https://api.anthropic.com/v1/messages`, `x-api-key: $ANTHROPIC_API_KEY`.
  - All requests go through an injectable transport seam (`_post_json`) so tests substitute a fake — no network in the test suite. Clear, actionable errors when a backend is unreachable / unconfigured / the model is missing.

- **`prompts.py`** — a compact system prompt embedding: the v3 schema, the distribution list, the expression-function list, and **2 few-shot examples** drawn from real configs (the coin-flip minimal config + one trimmed real domain). Kept small so 7B models stay on track. Plus the repair-prompt template and the explain-prompt template.

- **`compiler.py`** — `compile_config(question, *, n_simulations=None, max_repairs=3, **backend_opts) -> {config, valid, attempts, errors}`. Draft (JSON mode) → parse-guard → validate → if errors, append a repair message (errors + the offending config) and re-draft, up to `max_repairs`. Returns the last attempt with status; never raises on a bad model output — it reports.

- **`explain.py`** — `explain_results(question, config, results) -> str`. Answers the *original* question in plain language, grounded **only** in the stats/safety we pass in (explicit instruction + the numbers in the prompt). Falls back to the engine's deterministic `narrative` if the LLM is unavailable or errors.

### Validation reuse

The compiler reuses the existing config-validation logic (today duplicated across `mcp_server._validate_config` and `server.py`'s `/api/validate`). **Targeted cleanup:** factor that logic into one shared helper (e.g. `validation.py` or a function in `kernel`) that the compiler, the server, and the MCP server all call, so we do not create a third copy. Keep the change minimal and behavior-identical.

### CLI: `v3/sim_ask.py`

```
python3 sim_ask.py "Should I take an $8k/mo 6-month contract if there's a 30% chance it overruns?"
```

Flow: "Thinking…" → `compile_config` (show repair attempts in verbose) → `run_monte_carlo` → print the explanation + key stats (median, p10–p90) + safety verdict. Flags: `--backend`, `--model`, `--n`, `--seed`, `--save NAME` (persist to `domains/`), `--show-config`, `--json` (machine output), `--verbose`. Pure stdlib + `llm/` + `kernel`. If the backend is unavailable, print exact setup steps (install Ollama, `ollama pull <model>`) and the API alternative.

### Web "Ask anything" tab

- New tab in `static/index.html`: a labeled textarea ("Describe any decision or uncertain question…"), a Run button, and an optional advanced row (sims, backend). A "Thinking…" state while it works.
- New endpoint `POST /api/ask` in `server.py`: body `{question, n_simulations?, seed?}` → `compile_config` → `run_monte_carlo` → `explain_results` → returns `{question, config, results (stats/trajectories/histograms/safety/fitness/narrative), explanation, attempts, valid}`.
- UI renders: the plain-language explanation on top → the standard result views (reuse existing histogram/gauge/trajectory render) → a "Review / edit config" panel (reuse the wizard's JSON editor) → "Save as domain" (reuse `/api/save-domain`).
- If `llm/` is unconfigured/unavailable, `/api/ask` returns a clear error the UI surfaces ("LLM backend not available — start Ollama or set an API key"). Everything else in SimEngine keeps working.

## Data flow

```
[CLI / Ask tab]
      | question (+ optional n, seed)
      v
compile_config ----draft/repair---> backends.complete (json_mode)
      | valid config            ^                    |
      v                         |__ validate(errors)_|
run_monte_carlo  --> stats / safety / trajectories / histograms / narrative
      |
      v
explain_results --> backends.complete --> plain-language answer (fallback: narrative)
      |
      v
[CLI prints]  /  [/api/ask returns {config, results, explanation, attempts}]  /  [optional save-domain]
```

## Error handling

- Backend down / no key / model missing → clear actionable message in CLI and `/api/ask`; the rest of SimEngine is unaffected.
- Model returns non-JSON or an invalid config → treated as a validation failure → repair loop.
- Repair loop exhausted → return the closest config + the remaining errors and say what failed. Never emit silent garbage.
- Explanation constrained to the provided numbers; deterministic narrative is the fallback.

## Configuration (env vars)

- `SIMENGINE_LLM_BACKEND` = `ollama` (default) | `openai` | `anthropic`
- `SIMENGINE_LLM_MODEL` = model name (default: a small instruct model, e.g. `qwen2.5`)
- `OLLAMA_HOST` (default `http://localhost:11434`)
- `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1`)
- `ANTHROPIC_API_KEY`

## Testing (TDD, no network)

A fake injected backend drives every test:

- **backends:** request-building + response-parsing for each backend via the injected transport; unconfigured/unreachable error paths.
- **compiler:** repair loop converges (fake returns a bad config, then a good one → validates); `max_repairs` exhaustion returns errors; prompt assembly includes the schema + few-shot examples.
- **explain:** passes real stats, returns text; falls back to `narrative` when the backend fails.
- **sim_ask CLI:** arg parsing; end-to-end with a canned-config fake backend runs and prints; `--save` writes a domain; backend-missing prints setup help.
- **/api/ask:** handler with a fake backend returns `{config, results, explanation, attempts}`; backend-missing returns a clean error.
- **live smoke (optional):** if Ollama is running, one real question end-to-end.

## Boundaries — what stays true

- Core engine stays zero-dependency. `v3/llm/` is opt-in and stdlib-only (urllib + json). The core never imports it. CLAUDE.md carve-out added.
- Honest framing preserved: decision support / scenario analysis, never financial advice or trade signals — carried into the prompts and the explanation constraints.
- No frontend build step; the "Ask anything" tab is plain HTML/JS in the existing single-file UI.

## Build order (incremental, TDD)

Even though we build "both faces in one push," ship it as bounded, verifiable steps:

1. `llm/backends.py` + tests (fake transport).
2. `llm/prompts.py` + `llm/compiler.py` (draft + validate + repair) + tests.
3. Validation helper extraction (minimal shared `validate_config`).
4. `llm/explain.py` + tests.
5. `sim_ask.py` CLI + tests; live Ollama smoke.
6. `POST /api/ask` in `server.py` + tests.
7. "Ask anything" tab in `static/index.html`; manual UI verification.
8. Docs: guide note + README + CLAUDE.md carve-out; env-var reference.

## Future (out of scope now)

- Streaming progress in the UI.
- Caching / reusing generated configs.
- A "did the engine's answer match reality?" loop wiring `/api/ask` outputs into the calibration ledger.
- Hosted small-model inference under the commercial MCP.

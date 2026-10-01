# SimEngine Wiki

The home page for every document in `docs/`. Each page is listed exactly once,
under the section that says what it is for. The same index is served to AI
agents by the MCP server (`list_docs`, `search_docs`, `read_doc` tools and
`simengine://docs/...` resources), so **adding a page here is what makes it
reachable over MCP.** `v3/tests/test_docs_wiki.py` fails if a page under
`docs/` is missing from this index or if any link in it is broken.

Conventions for new pages:

- Dated work products (reviews, specs, plans, backtests) are named
  `YYYY-MM-DD-topic.md` and open with `date:` / `status:` lines.
- Living reference pages have no date in the name and are kept current.
- One `# Title` per page — it becomes the page title in `list_docs`.

## Guide

Plain-language path for people new to SimEngine. Read in order.

- [Start Here](guide/README.md) — overview of the guide and the order to read it in
- [What Is SimEngine?](guide/01-what-is-simengine.md) — why one number is a lie, and what to use instead
- [Quickstart: Your First Simulation](guide/02-quickstart.md) — run a real model in under two minutes
- [Reading the Results](guide/03-reading-the-results.md) — percentiles, bands, and the pass/fail safety flag
- [Who It Is For (and Why)](guide/04-who-its-for.md) — decisions this fits, decisions it doesn't
- [Explaining It to Others (Pitch Kit)](guide/05-explaining-it-to-others.md) — the words to use when explaining it fast
- [Model Your Own Decision](guide/06-model-your-own.md) — build a config from the smallest working example
- [Ask Anything & Track Your Predictions](guide/07-ask-and-track.md) — plain-language questions and the scored forecast ledger
- [Stress-Testing a Contract You Didn't Write](guide/08-contract-stress-test.md) — the consulting workflow for revenue-bearing contracts
- [Glossary](guide/glossary.md) — every term in plain language

## Reference

Contracts and integration docs for people and agents building on the engine.

- [Agent Integration Guide](../v3/AGENT_INTEGRATION.md) — how an AI agent builds, validates, runs, and interprets a simulation over HTTP
- [Schema Reference](schema-reference.md) — every domain-config field and distribution, in plain language
- [The Agent Decision Gate](decision-gate.md) — the `decide_under_uncertainty` MCP tool: proceed / escalate on outcome risk
- [Real-Time Data Feeds](feeds.md) — opt-in Polymarket Gamma adapter and its ToS boundaries
- [MCP Server Card (draft)](server-card.md) — registry-facing description of the MCP server; not published

## Evidence

Validation results and the claims they do (and do not) support.

- [FRED Monthly Calibration Backtest (2026-07-06)](backtests/2026-07-06-fred-monthly-calibration.md) — ~2,800 walk-forward forecasts scored with Brier / log-loss / CRPS; raw results in [the JSON file](backtests/2026-07-06-fred-monthly-results.json)

## Runbooks

Step-by-step operational procedures.

- [Publishing to the MCP Registry](PUBLISHING-MCP-REGISTRY.md) — PyPI + official MCP registry release steps and version lockstep

## Decisions & History

Why things are the way they are. Dated, newest last; superseded content stays
for the record.

### Reviews

- [Product Analysis & Refinement Report (2026-06-26)](reviews/2026-06-26-product-analysis.md) — source-verified defect audit of the decision surfaces
- [Prioritized Leverage Backlog (2026-07-06)](reviews/2026-07-06-leverage-backlog.md) — ranked next moves after the product analysis

### Go-to-market

- [Demand Probe](demand-probe.md) — the cheap 48-hour test of whether agent builders want the decision gate

### Design specs

- [Natural-Language Domains & LLM CLI (2026-06-01)](superpowers/specs/2026-06-01-nl-domains-and-llm-cli-design.md) — the `llm/` front door and `sim_ask.py`
- [Calibration Ledger (2026-06-27)](superpowers/specs/2026-06-27-calibration-ledger-design.md) — forecast capture and reliability diagram
- [Scenario Sweep + Input Diff (2026-06-28)](superpowers/specs/2026-06-28-scenario-sweep-design.md) — sweeping one input and diffing scenarios in the UI
- [Hosted MCP Revenue Pipeline (2026-07-11)](superpowers/specs/2026-07-11-hosted-mcp-revenue-pipeline-design.md) — self-serve path from MCP discovery to paid tier

### Implementation plans

- [Calibration Ledger Plan (2026-06-28)](superpowers/plans/2026-06-28-calibration-ledger.md) — task-by-task plan for the ledger spec
- [Hosted MCP Pipeline Phase 0 Plan (2026-07-11)](superpowers/plans/2026-07-11-hosted-mcp-pipeline-phase0.md) — PyPI package, registry listing, landing page, demand probe

Some specs cite notes under `~/wiki/` (for example
`~/wiki/decisions/2026-04-15-simengine-gtm-options.md`). Those live in a
private notes folder outside this repository and are not served over MCP.

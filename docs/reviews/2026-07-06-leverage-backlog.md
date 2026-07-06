# SimEngine — Prioritized Leverage Backlog

date: 2026-07-06
branch: feat/fable5-improvements (off feat/scenario-sweep @ dc7e167)
predecessor: docs/reviews/2026-06-26-product-analysis.md

## Triage baseline (verified against current source, not assumed)

- `make test`: **286 tests, OK (5 skipped)** on dc7e167.
- Every P1 correctness defect and P2 UX item from the 2026-06-26 audit is **already fixed
  and merged** (commits 0ed564f, aa0dab3, 5781afa, df56af2, 8cc5534). Verified in source:
  condition aliases (`kernel.py` BELOW_CONDITIONS/ABOVE_CONDITIONS), `best_controls`
  serialization, integer tunables, CRN sensitivity, binary-metric narrative, tunable/fitness
  validation, `setMain()` scroll reset, Ask AbortController.
- The calibration ledger is fully productized since the audit (reliability curve, ECE, gated
  report, Predictions UI, one-click forecast tracking).
- Repo grep confirms **no** "async Tasks handle" claim and **no** "only general
  decision-intelligence MCP server" overclaim anywhere in README/docs/v3 — both flagged
  risks are clean in this repo (any remaining instances live outside the repo, e.g. drafts).
- Still open from the audit's low-severity tail (verified still present):
  - Schema `chance_constraints.condition` enum is `["below","above"]` while the kernel
    accepts `lt/</lte/<=/under/gt/>/gte/>=/exceeds`; schema description text still says
    "any other condition value counts v > threshold," which is no longer true (unknown
    now raises). `AGENT_INTEGRATION.md`'s worked example uses `"condition": "<"` —
    schema-invalid today. Contract drift on the agent-facing surface.
  - `_student_t` does `range(df)` → non-integer `df` (e.g. 4.5) raises TypeError
    (kernel.py:69).
  - `deterministic_baseline` handles `dist=="choice"` which is not a registered sampler
    (diagnostics.py:378) — dead branch.
  - Native reducer failures fall back silently (`except Exception` → Python path), which is
    graceful but unobservable; a `SIMENGINE_DEBUG_NATIVE=1` stderr note would make
    divergence triage possible.

## Ranked backlog (leverage toward first paying use)

### 1. Calibration backtest against real historical data — lane: technical trust — **THIS SESSION**

The single most-repeated gap across every review since March (Sonnet panel, ChatGPT-4o,
Deep Research counterpaper, wiki open questions): *no documented validation against
real-world data*. It gates the academic paper venue, weakens every sales claim, and is the
counterpart of the "arms-length proof" push — a backtest on public data nobody at Venture
Horizon authored is itself arms-length evidence.

Verified feasible today: FRED serves full-history CSVs keyless
(`fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE`), so the harness can stay
stdlib-`urllib`, opt-in network (same posture as `v3/feeds/`), with committed data
snapshots so the backtest itself runs offline and reproducibly.

Shape: `v3/backtest.py` — rolling-origin monthly binary forecasts (e.g. "does unemployment
rise next month?", "does MoM CPI inflation exceed 0.25%?", "does industrial production
fall?") where each forecast is produced by the **real engine path** (config →
`run_monte_carlo` → indicator-metric mean), scored with the **existing** `calibration.py`
(Brier, log-loss, ECE, reliability curve) against a walk-forward climatology baseline.
Output: JSON results + a dated report under `docs/backtests/`. Honest framing: this
validates that engine-produced probability distributions are *calibrated*, not that they
beat the market — ECE and the reliability curve are the headline numbers, Brier skill vs
climatology the secondary one.

### 2. Scenario sweep + input diff — lane: UX/demo — **THIS SESSION**

Fully designed and approved (docs/superpowers/specs/2026-06-28-scenario-sweep-design.md),
zero open questions, client-side only. Turns the existing scenario comparison into the
decision tool the consulting demos need: "sweep baristas 1–6 and show me the table" is the
moment SimEngine reads as a product instead of an engine. Phase C (consulting) is the only
live revenue channel, so demo legibility is direct GTM leverage. Implement per spec:
`sweepValues` / `captureInputs` / sweep modal / `runSweep` / input-diff section in
`compareScenarios`, static-contract test, live smoke.

### 3. llms.txt + MCP server card groundwork — lane: GTM — **THIS SESSION**

The registry publish is gated on Tony's decision, but the *artifacts* should be ready so
the decision is one `git push` away, and so any agent crawling the repo/server gets the
accurate story. Deliverables: `llms.txt` at repo root (also served at `GET /llms.txt` so
local agents self-orient), and `docs/server-card.md` — the MCP server card draft using the
defensible positioning ("validated, schema-contracted Monte Carlo across 19 domains with a
numeric calibration ledger — now with a published historical backtest"), explicitly marked
DRAFT/unpublished. No external publication in this session.

### 4. Agent-contract accuracy fixes — lane: technical trust — **THIS SESSION**

Small, but they're drift on the exact surface (schema + agent guide) we tell agents to
trust: widen the schema `condition` enum to the kernel's accepted aliases, fix its stale
description, and guard `_student_t` for non-integer `df` (round; it's a sampler, not a
contract change). Rides along with #3's accuracy theme.

### 5. Contract stress-test playbook — lane: GTM — **THIS SESSION** (shipped after #1–#4)

Shipped as `docs/guide/08-contract-stress-test.md` (linked from the guide index): a
walkthrough generalizing the paint_responsibly_jv workflow so the **arms-length
proof** — stress-testing a contract Tony didn't author — is a repeatable 2–4 hour
process: clause-to-config intake mapping, chance constraints carrying the contract text
as `rationale`, the four interrogation questions (party downside, milestone-vs-ramp,
sensitivity, sweep-to-counter-proposal), and the two-document output pattern (internal
analysis + counterpart-safe summary). The remaining arms-length step is business, not
code: source a third-party contract and run the playbook.

### 6. Backtest expansion: French Data Library equity sleeve — lane: technical trust — backlog

Add a monthly equity-return sleeve (Ken French market factor) to the #1 harness: fat-tail
(student_t) vs normal input distributions, CRPS on continuous outcomes rather than only
binary Brier. Strengthens the paper (RQ1 prequential calibration) and the claim ledger.
Blocked only by session time; the harness from #1 is designed to take new series.

### 7. Native-path observability — lane: technical trust — backlog

`SIMENGINE_DEBUG_NATIVE=1` → stderr warning when the native reducer raises and the engine
falls back to Python. Keeps the graceful-fallback contract, makes silent divergence
triageable. Small.

### 8. Diagnostics dead-branch cleanup — lane: technical trust — backlog

Remove/replace the unregistered `choice` branch in `deterministic_baseline`
(diagnostics.py:378). Cosmetic correctness.

### 9. PyPI packaging (`pipx run simengine`) — lane: GTM — backlog, decision needed

Every review's "how do I deploy this" question. Zero-dep makes packaging trivial
(`pyproject.toml`, no deps), but it touches the brand ("no pip install" is the tagline —
packaging must be framed as *additional* distribution, not a requirement) and the
open-core boundary. Recommend deciding after the demand probe, not before.

### 10. 2-D sweeps, sweep persistence, categorical sweeps — lane: UX — backlog

Explicitly YAGNI'd in the sweep spec. Revisit only if consulting demos ask for them.

## Explicitly not doing (settled or gated)

- x402 per-call pricing — evaluated and rejected (stdio MCP; wrong fit). Not revisiting.
- MCP registry publish, demand-probe outreach, social posts — gated on Tony.
- Pricing tiers / LICENSE-COMMERCIAL.md — business decisions; recommendation only:
  the backtest report (#1) is the artifact that should anchor any future pricing page's
  trust section.

# SimEngine codebase review — 2026-10-03

branch: `review/2026-10-03-kernel-hardening` (off `fix/canonical-config-hash` @ 39d265b, which is 3 commits ahead of `main` and already pushed but unmerged)
predecessors: `docs/reviews/2026-06-26-product-analysis.md`, `docs/reviews/2026-07-06-leverage-backlog.md`
trigger: pre-work for using the engine as the fair-value layer of a prediction-market stack (Kalshi / Polymarket US)

## Baseline (verified, not assumed)

- `make test` on 39d265b: **324 tests OK, 4 skipped** (pure-Python path).
- Same suite under `.venv` with the Rust extension importable: OK. `cargo test -p simengine-core --lib`: 10 passed.
- Working tree clean; last code commit 2026-07-24, last commit of any kind 2026-09-01.
- Every item on the 2026-07-06 backlog marked THIS SESSION is in the tree (backtest harness + FRED snapshots, scenario sweep, llms.txt, server card, condition-alias schema fix, student_t df rounding, contract stress-test guide). Backlog #7 (native observability) and #8 (dead `choice` branch) are still open.

## The March picture is stale

The web-chat conversation that prompted this review assumed the engine was still where v3 left it in March. Each assumption, checked against source:

| Assumed | Actual |
|---|---|
| `eval()` still in the expression evaluator, AST migration deferred | `eval()` is still the kernel's evaluator (`kernel.py eval_expr`), with a replaced `__builtins__`. An AST evaluator exists in `diagnostics.py safe_eval_expr` but the kernel does not use it. `validation.py` statically rejects attribute access, but only `/api/validate` and the LLM compiler call it. See defect 1. |
| Pure stdlib, no numpy, loops won't keep up | Stdlib core is deliberate and documented as the brand. Opt-in Rust crates (`crates/`) already handle batch sampling, reducers, safety and histograms, with graceful fallback. Nothing numpy-shaped is needed. |
| Paths not exported, only summary stats | `run_monte_carlo` returns `raw_metrics`: every metric's per-run values, aligned by run index. The joint distribution across metrics is already available; book-level CVaR on a P&L metric works today via `compute_cvar`. Per-step paths are reduced to p10/p50/p90 bands only. |
| No proper scoring rules | `calibration.py`: Brier, log-loss, CRPS, reliability curve, ECE, sqlite ledger, wired to `/api/forecast`, `/api/resolve`, `/api/forecasts` and the Predictions UI. |
| Bayesian updates designed but not running | `bayesian.py` runs (Beta-Binomial, Gamma-Poisson, Normal-Normal), wired to `/api/update` and the `update_bayesian` MCP tool. The feed → prior → posterior bridge had a real bug, though. See defect 4. |
| Probably no tests beyond the smoke test | 324 unittest cases across 33 files, including native-integration, schema-contract, packaging-invariant and backtest suites. |

Net: this is an upgrade pass on a mature codebase, not a rescue.

## Defects verified by probe and fixed on this branch

Each was reproduced against the unpatched kernel first. Each has a regression test in `v3/tests/test_kernel_hardening.py`.

### 1. Expression allow-list was advisory, not enforced — HIGH (security)

`validation.py check_expression_names` rejects dotted/attribute access, but nothing on the `/api/simulate` inline-config path, the MCP `simulate` tool, or library use calls it. The kernel compiled and `eval()`'d whatever string it was given with only `__builtins__` swapped out, and replacing builtins does not stop attribute introspection on the float values that live in `state`. With LLM-generated configs now a first-class input (`/api/ask`), an unscreened expression is the wrong default.

Fix: `kernel.py` now screens every expression's AST before compile (`expression_violation`, `_FORBIDDEN_EXPR_NODES`: Attribute, Subscript, Lambda, comprehensions, walrus, starred, f-strings, await/yield, and any `__dunder__` name). `DomainConfig.__init__` walks step_logic, accumulators, metrics and fitness components and raises `ValueError` on the first violation, which the server already maps to HTTP 400 and the MCP layer surfaces as a tool error. `eval_expr` refuses the same syntax independently (defense in depth: returns 0, the existing bad-expression contract). All 17 shipped domains load unchanged. Verified: `POST /api/simulate` with `x.__class__` in step_logic → `400 {"error": "step_logic[0]: Attribute is not allowed in expressions"}`.

Behavior change: a config using forbidden syntax used to run and silently evaluate that expression to 0; it now fails loudly at load. That is the intended contract (`docs/schema-reference.md` already listed these constructs as errors).

Residual, not fixed: CPU exhaustion through legal arithmetic (`**` with huge operands, `sum(range(...))`) and through unbounded `n_simulations`/`n_steps` on `/api/simulate`. The server binds to 127.0.0.1 so this is a local concern today; it must be capped before any hosted endpoint.

### 2. Correlated `student_t` variables sampled as constant 0 — HIGH (silent wrong answer)

`apply_correlation_to_sample` had no `student_t` branch and fell through to `return base_value`, which callers pass as 0. Any config listing a fat-tailed variable in `correlations` (the exact combination the investment-portfolio domains are built for) got a constant zero for that variable with no error. Probe: student_t mean 10, rho 0.5 with a normal → mean 0, std 0.

Fix: Gaussian-copula t sample (correlated z over an independent chi-square), consistent with the marginal sampler. Test asserts mean within [8, 12] and sample correlation > 0.4 at rho 0.8.

### 3. Safety penalty rewarded negative fitness — HIGH (optimizer correctness)

`compute_fitness` applied `total *= max(0.1, 1 - 0.3 * violations)`. For a negative score that is a shrink toward zero: −100 with one violation became −70 and outranked the compliant −100. Any domain whose objective can go negative (ending cash, P&L, net margin) had its optimizer prefer constraint violations in exactly the region where constraints matter.

Fix: same factor, applied sign-safely (negative scores are pushed further from zero by the same proportion: −100 → −130). Positive-fitness behavior is unchanged, so existing optimizer results for positive objectives do not move.

### 4. `feeds.polymarket` prior strength was decorative — MEDIUM

`prior_variable(p, strength=...)` documented `strength` as "how much to trust the market", but `bayesian.beta_binomial_update` rebuilt the Beta prior from the triangular mode with a hardcoded `n_pseudo = 10`. Probe: strength 5 and strength 200 produced identical posteriors. The exact lever the prediction-market plan depends on (how much to trust the market versus the model) did not exist.

Fix: `beta_binomial_update` / `gamma_poisson_update` take `n_pseudo`; `prior_variable` records `calibration.prior_strength`; `update_parameter` passes it through (and rejects non-positive values). Variables without a declared strength keep the old defaults, so existing update results are unchanged.

### 5. Metric stats rounded to 2 dp — MEDIUM (precision)

`_compute_stats_python` and the Rust reducer both rounded mean/median/std/p10/p25/p75/p90 to hundredths. Fine for dollars, destructive for any metric on a 0..1 scale: a rate of 0.1234 reported as 0.12 on every statistic. (`binary_prob` was already 4 dp, which is why the backtest was unaffected.) Now 4 dp in both reducers (`stats.rs` rebuilt, `_checkpoint_stats` in diagnostics aligned). Pure-Python and native paths agree within Monte Carlo noise on `business_pipeline_v3` (72,339 vs 72,744 mean annual revenue).

### 6. Poisson sampler broke above λ ≈ 745 — LOW (edge case)

Product-form Knuth: `exp(-λ)` underflows to 0, so the loop ends when the running product underflows instead, returning ~720 for any large λ (probe: λ = 2000 → 723). Replaced with the exponential inter-arrival form, exact for all λ. The native batch sampler was unaffected.

### 7. Seed reproducibility was not thread-safe — MEDIUM (reproducibility)

`run_monte_carlo` seeds and draws from the process-global `random` module, and `server.py` runs on `ThreadingHTTPServer`. Two concurrent `/api/simulate` calls interleaved draws, so the same seed could give different results. Simulations are CPU-bound under the GIL anyway, so serializing them costs nothing: `kernel.SIM_LOCK` (reentrant) now wraps `run_monte_carlo`, and the convergence loop in diagnostics takes the same lock. Test runs six threads with one seed and asserts byte-identical stats.

### 8. Optimizer scored candidates on different random draws — MEDIUM (optimizer quality)

Every GA candidate was simulated on fresh draws, so selection partly rewarded sampling luck (winner's curse), and a seeded `evolve()` was not reproducible. Fix: common random numbers per generation (the same idea the sensitivity analysis already uses). `_worker` accepts an optional seed; `evolve` derives a `ga_seed` from the config seed (or draws one) and stamps it in the manifest. Elites are re-scored each generation on that generation's draws, so one lucky evaluation cannot lock in as `best_ever`. Seeded `evolve()` is now deterministic (tested). The legacy 4-tuple `_worker` call still works.

### 9. Version strings drifted — LOW (release hygiene)

`kernel.py make_manifest` stamped `kernel_version: "3.0.0"` and `mcp_server.py` advertised `serverInfo.version: "3.0.0"` while the package is 3.0.1. Both now read `kernel.KERNEL_VERSION`, and `test_packaging_invariants` enforces it alongside pyproject / `__init__` / server.json.

Also: `_COMPILED_EXPR_CACHE` was unbounded (one entry per distinct expression string ever seen by a long-running server); now capped at 4096 entries. Bare `except:` in `eval_expr` narrowed to `except Exception`.

## Verified issues, not fixed (need a decision or are out of scope)

- **CORS `*` on a localhost engine.** Any web page open in the user's browser can POST to `localhost:8420`: burn CPU, write files via `/api/save-domain` (name-sanitized, but still a write), log forecasts. The single-file UI is same-origin and does not need CORS. Recommend dropping the wildcard, or gating POST behind a token, before the hosted service exists. Not changed here because `AGENT_INTEGRATION.md` documents CORS as a feature and that is a product call.
- **`mcp_server.py` still carries its own `_validate_config` copy** (the `validation.py` docstring asks for it to be folded in). Drift risk on the agent-facing surface. Mechanical change, deferred to keep this diff reviewable.
- **Native reducer returns metrics in sorted order; Python preserves insertion order.** Only visible effect: `evolve`'s verbose "top metric" column picks a different metric under native. Cosmetic.
- **`cholesky` silently clamps a non-positive-definite correlation matrix** (`sqrt(max(0, val))`), so an inconsistent set of pairwise rhos runs with correlations that are not what was asked. Should validate and reject.
- **Rate-style Beta-Binomial observations assume 20 trials each** (`bayesian.py`). Documented in code but invisible to the API; `(successes, trials)` tuples should be the recommended form.
- **MCP `simulate` returns `fitness: 0` when no objective is defined; the HTTP API returns `null`.** Minor contract inconsistency.
- **Backlog #7 / #8** (native fallback observability, dead `choice` branch) remain open.

## Prediction-market readiness

What the market layer in the web-chat sketch needs, mapped to what exists:

| Sketch entity | Status in repo | Gap |
|---|---|---|
| Event + Contract (predicates over one outcome space) | A domain config is the event; each contract is an indicator metric (`100 if lo <= x < hi else 0`); all priced from one run via `raw_metrics`, run-aligned | None for pricing. Per-step paths are not exported, so path-dependent contracts (e.g. "touches X before resolution") need an accumulator per predicate. |
| Forecast with `p_lo` / `p_hi` | `binary_prob` is a point estimate | Add a bootstrap CI over `raw_metrics` (cheap, pure stdlib). This is the honesty check that kills most "found edge" stories. |
| Calibration vs market | Ledger scores the model only | Add `p_market_at_ts` to the ledger and report Brier skill vs market, the way `backtest.py` already reports skill vs climatology. |
| Blend weight `w` (model vs market) | `prior_strength` now works end to end (defect 4) | Learn `w` from the calibration table; today it is a manual knob. |
| Book-level CVaR from joint paths | `compute_cvar` over a P&L metric gives exactly this, since `raw_metrics` are run-aligned | None. |
| Fees as a function per venue | None | New, small. |
| BookSnapshot ingest | `feeds/polymarket.py` reads Gamma (read-only, stdlib) | **No Kalshi adapter, by policy:** `docs/feeds.md` records that Kalshi's data terms restrict software/AI use without written consent. The web chat recommended Kalshi as the venue; confirm the current terms before writing a single line against their API. Polymarket US terms also need checking before anything beyond read-only use. |
| Sizing (fractional Kelly under CVaR cap) | CVaR constraints + optimizer exist | Policy config, not engine work. |
| Kill switch (force `action = none`) | `decide_under_uncertainty` already refuses to name contracts or trade (`docs/decision-gate.md` positioning guardrail) | Keep execution out of this repo entirely. |

Recommended order, unchanged in spirit from the sketch: (1) bootstrap CI on indicator metrics, (2) `p_market` column + skill-vs-market in the ledger, (3) a bucket-market domain config priced from one run, paper-traded through the existing ledger for a month, (4) only then fees and sizing. All of (1)–(3) are inside the stdlib promise.

## Verification performed

- `make test` (pure Python): **345 tests OK, 4 skipped**.
- Same suite with the rebuilt native extension (`.venv`): **345 OK, 5 skipped**.
- `cargo test -p simengine-core --lib`: 10 passed.
- HTTP smoke on port 8421: `/api/health` OK; forbidden expression → 400 with a named location; `business_pipeline_v3` → 200 with 4 dp stats.
- `scripts/smoke_mcp_stdio.py`: `SMOKE OK (9 tools, 17 domains)`.
- Pure-Python vs native parity on a shipped domain: within Monte Carlo noise.

## Reviewing this branch

```bash
git diff fix/canonical-config-hash...review/2026-10-03-kernel-hardening --stat
make test
```

The three behavior changes a reviewer should consciously accept: forbidden expression syntax now raises at load instead of evaluating to 0; negative fitness scores are penalized downward instead of upward; metric stats carry 4 decimals instead of 2.

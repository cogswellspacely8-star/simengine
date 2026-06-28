# Calibration Ledger — Capture + Reliability (Design)

date: 2026-06-27
status: approved (brainstorming) — pending spec review before implementation plan
branch: feat/calibration-ledger

## Context

SimEngine already ships a calibration ledger: `v3/calibration.py` (`CalibrationLedger`
over sqlite — `record` / `resolve` / `score`, with Brier and log-loss; a `crps_sample`
helper exists but is unused), the `/api/forecast | /api/resolve | /api/forecasts`
endpoints, and a **Predictions** modal that shows an aggregate "Track record: N resolved
· Brier · log-loss", a forecast table, Hit/Miss grading, and a manual add-prediction form.

The ledger is the product's trust differentiator — "the only thing separating a calculator
that emits plausible numbers from a forecasting instrument is a track record scored against
reality." Three gaps keep it from being that:

1. **Capture** — forecasts are typed by hand. Nothing flows from a simulation into the
   ledger, even though a binary-indicator simulation (e.g. BTC's "P(>$70k by Jun 30)")
   *is* a dated forecast with a `binary_prob` (added in P1) and an implied resolve date.
2. **Visualize** — only an aggregate Brier number. No reliability diagram (the signature
   calibration visual: predicted probability vs observed frequency, by bucket).
3. **Close the loop** — unresolved forecasts past their `resolve_by` date are not surfaced.

This spec builds **gaps 1 and 2 as one loop** (data flows in, calibration becomes visible).
Gap 3 (resolve-by nudges) is a separate, later track.

## Decisions (from brainstorming)

- **Scope:** capture + reliability visualization. Resolve-by nudge deferred.
- **Capture trigger:** explicit one-click **"Track this forecast"** (never auto-log every
  simulation — that would pollute the ledger and make the Brier number meaningless). Applies
  to both simulation results and Ask answers.
- **Eligibility:** only binary-indicator metrics (those carrying `binary_prob`). Continuous
  metrics are not binary forecasts and cannot be Brier-scored.
- **Resolve-by:** an inline form pre-fills from an optional domain `resolve_by` field if the
  author declared one, else the user picks a date.
- **Small-N honesty:** the reliability diagram is **gated** — it renders only once
  `n_resolved >= MIN_N` (default 10). Below that, a progress line ("4/10 resolved — curve
  unlocks at 10") plus the aggregate Brier with the 0.25 = coin-flip anchor. Every bin labels
  its sample count.

## Architecture

Reliability math lives in `v3/calibration.py` (pure stdlib, unit-tested alongside the
existing Brier/log-loss). The diagram renders on a `<canvas>` in the existing single-file UI,
following the histogram/trajectory drawing pattern. Capture reuses the existing
`/api/forecast` path. No new endpoint; no DB migration — the `forecasts` table already has
`metric`, `config_hash`, and `resolve_by` columns and `record()` already accepts them.

## Components

### 1. `calibration.py` (scoring — new, pure stdlib)

- `reliability_curve(self, n_bins=10) -> list[dict]`
  Bin every **resolved** forecast by `predicted_prob` into `n_bins` equal-width buckets
  `[0,0.1), [0.1,0.2), …, [0.9,1.0]` (the last bin includes 1.0). For each **non-empty** bin
  return `{"lo", "hi", "count", "mean_predicted", "observed_freq"}` where `mean_predicted` is
  the mean predicted probability in the bin and `observed_freq` is the mean realized outcome.
  Empty bins are omitted. Returns `[]` when nothing is resolved.

- `expected_calibration_error(self, n_bins=10) -> float | None`
  `ECE = Σ_bins (count / N) · |observed_freq − mean_predicted|` over the curve. `None` when
  no resolved forecasts.

- `calibration_report(self, min_n=10, n_bins=10) -> dict`
  ```
  {"n", "brier", "log_loss", "base_rate", "ready", "min_n", "curve", "ece"}
  ```
  `n` = resolved count; `base_rate` = mean outcome; `brier`/`log_loss` reuse existing
  functions (None when `n == 0`); `ready = n >= min_n`; `curve` and `ece` are populated only
  when `ready`, else `None`. `MIN_N = 10` as a module constant.

  `score()` is left unchanged (backward compatibility — the existing UI line uses it).

### 2. Domain schema (`schema/domain.schema.json`)

Add an optional top-level `resolve_by` (string, ISO date) — additive, not required. Lets an
authored binary domain declare its resolution date (e.g. BTC → `"2026-06-30"`) so the Track
form pre-fills it. No effect on the engine.

### 3. Server (`server.py`)

- `/api/forecasts`: extend the response from `{forecasts, score}` to
  `{forecasts, score, calibration}` where `calibration = ledger.calibration_report()`.
  Backward compatible (adds a key; `score` stays).
- `/api/forecast`: no change — it already records `question, predicted_prob, metric,
  config_hash, resolve_by`. The UI now sends `metric` and `resolve_by`.

### 4. UI (`static/index.html`)

- **Track button (results + Ask).** On each binary-indicator stat card (and the Ask result
  table), a "Track this forecast" affordance opens a **small modal dialog** (consistent with
  the existing Predictions/Ask/New modals, reusing the add-prediction form fields) pre-filled
  with: question ← `currentConfig.context.decision` (or the humanized metric label), prob ←
  `binary_prob`, resolve-by ← `currentConfig.resolve_by` if present else blank. The user
  confirms/edits, then submit → `POST /api/forecast` with `{question, predicted_prob,
  resolve_by, metric}`, a toast confirms, and the dialog closes.
- **Predictions modal.** Above the existing table: the Brier/log-loss/base-rate line, then
  either (a) a `<canvas>` reliability diagram drawn by a new `drawReliability(canvas, curve)`
  — observed-vs-predicted points, the y=x perfect-calibration diagonal, each point labeled
  with its bin count, plus the ECE number — when `calibration.ready`; or (b) the progress
  line "N/MIN_N resolved — calibration curve unlocks at MIN_N." when not ready.

## Data flow

```
simulate / ask  ->  stats[m].binary_prob (P1)
   -> user clicks "Track this forecast" -> inline form (prefilled)
   -> POST /api/forecast {question, predicted_prob, resolve_by, metric}
   -> CalibrationLedger.record(...)            [existing]
   ... later: user grades Hit/Miss -> /api/resolve  [existing]
GET /api/forecasts -> {forecasts, score, calibration_report}
   -> Predictions modal: aggregate line + (gated) reliability diagram + ECE
```

## Error handling

- `n == 0`: `calibration_report` returns `brier/log_loss/base_rate/curve/ece = None`,
  `ready = False`; the UI shows the existing "no predictions graded yet" copy.
- Empty bins are omitted from the curve; a curve may legitimately have fewer than `n_bins`
  points.
- `reliability_curve`/`expected_calibration_error` never call `brier_score`/`log_loss` (which
  raise on empty); they guard on the resolved set themselves.
- Missing `resolve_by`: allowed (nullable column); the forecast logs without a date and the
  future nudge simply can't include it.
- A binary metric with no `context.decision` falls back to the humanized metric name as the
  question.

## Testing

- **calibration.py (TDD, stdlib unittest):**
  - `reliability_curve`: a hand-built ledger with known predicted/outcome pairs → expected
    per-bin `count / mean_predicted / observed_freq`; empty bins omitted.
  - `expected_calibration_error`: hand-computed ECE on the same fixture; `None` on empty.
  - `calibration_report` gating: `n < MIN_N` → `ready False`, `curve/ece None`; `n >= MIN_N`
    → `ready True`, curve present; `n == 0` → all-None shape.
  - capture round-trip: `record(question, p, metric=..., resolve_by=...)` then
    `all_forecasts()` returns the `metric`/`resolve_by` intact (extends `test_calibration` /
    `test_api_forecast`).
- **Server:** `/api/forecasts` response contains a `calibration` key with the report shape.
- **UI (static-contract, `test_static_ui_layout` or a new file):** `index.html` contains the
  "Track this forecast" affordance, the reliability `<canvas>` + `drawReliability`, and the
  gate/progress copy.

## Out of scope (YAGNI)

- Resolve-by nudges / "due for grading" list (the next calibration track).
- Auto-resolve via the existing Polymarket feed.
- CRPS / continuous-metric calibration.
- `config_hash` dedup of repeat forecasts (simulate has no manifest hash today).
- Per-bin Wilson confidence intervals (gate + counts was chosen instead).

## Open questions

None — all resolved in brainstorming (gate threshold 10; capture on both simulate and Ask;
out-of-scope list above).

# Scenario Sweep + Input Diff (Design)

date: 2026-06-28
status: approved (brainstorming) — pending spec review before implementation plan
branch: feat/scenario-sweep

## Context

SimEngine already has scenario comparison in the single-file UI:
`saveScenario()` snapshots the current run into `scenarios[] = [{name, results, color}]`;
`compareScenarios()` renders a metrics-side-by-side table (best/worst highlighting,
lower-is-better detection), a safety/fitness grid, and overlaid distribution histograms;
`renderScenarioBar()` / `viewScenario()` / `removeScenario()` navigate them. The current
workflow is manual: adjust a control → Run → Save Scenario, repeat, then Compare.

Two gaps keep it from being a decision tool:

1. **No input diff.** The comparison shows outcomes but never *what differs* between
   scenarios. You see each scenario's metrics but not "A = 2 baristas, B = 3 baristas" — a
   comparison that hides the levers is hard to act on.
2. **Manual, one-at-a-time.** To compare baristas 1–6 you hand-adjust, run, and save six
   times. There is no "sweep this control across values."

This spec adds a **control sweep** (auto-run a control across a range and compare) and an
**input-diff** section, turning the existing comparison into a decision tool. It also folds
in one targeted fix: `compareScenarios` writes `main.innerHTML` directly, skipping the P2
`setMain` scroll-reset, so its output can render off-screen.

## Decisions (from brainstorming)

- **Execution:** client loop over the existing `/api/simulate` (no new endpoint). Each swept
  value becomes a scenario; reuse `compareScenarios()`.
- **Value spec:** min / max / step, pre-filled from the chosen slider, capped at
  `SWEEP_MAX = 12` values (Run disabled when the spec yields >12 or <2 — no silent truncation).
- **Sweepable set:** any sidebar slider (controls AND parameters/exogenous), with controls the
  typical target.
- **Sweep replaces** the scenario set (clears `scenarios[]` first) so you compare exactly the
  swept values.
- **Input diff:** show *all* inputs that differ across the compared scenarios (controls,
  parameters, exogenous), swept control emphasized; self-contained per-scenario snapshot.

## Architecture

Fully client-side, in `v3/static/index.html`. No server or schema change. New code: a sweep
modal + value generation + the per-scenario input snapshot + the input-diff render. Everything
else reuses the existing `scenarios[]` array, `/api/simulate` (via `collectOverrides`), and
`compareScenarios()`.

## Components (all in `v3/static/index.html`)

### 1. `sweepValues(min, max, step) -> number[]`
Pure helper. Returns `min, min+step, … ≤ max` inclusive. Count is computed as
`floor((max - min) / step + 1e-9) + 1` (epsilon absorbs float error so e.g. 1→6 step 1 gives
exactly 6 values), each value `round(min + i*step, 6)` to avoid float drift (158.99999).
Returns `[]` for invalid input (step ≤ 0, max < min, non-finite). Does NOT itself cap — the
caller checks length against `SWEEP_MAX`.

### 2. `captureInputs() -> {path: value}`
Pure helper. Reads every `.param-slider[data-path]` and returns a resolved snapshot
`{dataPath: parseFloat(value)}` of ALL sliders (not just deltas), so each scenario carries its
complete input set independent of later edits.

### 3. Sweep modal (`openSweep()`)
A "Sweep…" button beside Save Scenario / Compare opens a modal:
- a `<select>` of the current sliders (option value = `data-path`, label = the slider's label);
- min / max / step number inputs, pre-filled from the selected slider's range and current value;
- a live "→ N runs" preview that recomputes on input and disables **Run Sweep** when
  `N < 2` or `N > SWEEP_MAX`;
- **Run Sweep** calls `runSweep(path, min, max, step)`.
Built with the existing modal/form classes; values read in JS (no quote-unsafe attribute
interpolation — follow the calibration `jsStr`/value-via-JS pattern).

### 4. `runSweep(path, min, max, step)`
- `const vals = sweepValues(min, max, step)`; guard `2 ≤ vals.length ≤ SWEEP_MAX`.
- Clear `scenarios = []`; record `_sweepPath = path` (so the diff can emphasize it).
- For each `v` (index `i`): `override = {...collectOverrides(), [path]: v}`; POST `/api/simulate`
  with that override; show progress ("Sweeping {var}: run {i+1}/{N}…"); on success push
  `{name: "{varName} = {v}", results: data, color: SCENARIO_COLORS[i % …], inputs: {...captureInputs(), [path]: v}}`.
- If any run errors, abort the sweep, restore nothing destructive (scenarios already cleared —
  acceptable; show which value failed), and toast the error.
- After all runs: `compareScenarios()`.

### 5. `saveScenario()` — extend
Capture `inputs: captureInputs()` into the pushed scenario object (one-line addition); nothing
else changes.

### 6. `compareScenarios()` — extend + fix
- Build an **Inputs** section ABOVE the metrics table: union the paths across all compared
  scenarios' `inputs`; for each path whose values are not all equal, render a row
  (label = `path.split('.')[1]` humanized, per-scenario values via `fmt`), the `_sweepPath`
  row emphasized. If no inputs differ, omit the section.
- Replace the direct `main.innerHTML = html` with `setMain(html)` (P2 scroll-reset) — but keep
  the `requestAnimationFrame(drawCompareHistograms…)` call after it.

## Data flow

```
pick control + min/max/step (modal)
  -> sweepValues() -> [v0..vN]  (capped at SWEEP_MAX)
  -> for each v: collectOverrides()+{path:v} -> POST /api/simulate
       -> scenarios.push({name, results, color, inputs: captureInputs()+{path:v}})
  -> compareScenarios(): Inputs-diff section + metrics table + safety + overlaid histograms
```

## Error handling

- `sweepValues` returns `[]` on step ≤ 0 / max < min / non-finite → modal disables Run.
- `N > SWEEP_MAX` or `N < 2` → Run disabled, preview shows the count and the limit.
- No sliders in the current domain (no sweepable variable) → the Sweep button (shown alongside
  the other scenario buttons once a domain is loaded) opens a modal whose dropdown is empty and
  whose Run is disabled, showing "No adjustable variables to sweep."
- A `/api/simulate` failure mid-sweep → abort, toast "Sweep failed at {var}={v}: {error}", leave
  whatever scenarios completed (do not auto-open compare on an aborted sweep).
- Input-diff with a single scenario or all-identical inputs → section omitted (no empty table).

## Testing

This feature is client-only JS; there is no new Python logic, so coverage is:
- **Static-contract** (`v3/tests/test_scenario_sweep_ui.py`, new): `index.html` contains the
  Sweep button + `openSweep`, `function sweepValues(`, `function runSweep(`, `function captureInputs(`,
  the `SWEEP_MAX` cap, an `inputs:` field on scenario pushes, and `compareScenarios` using
  `setMain` (regression guard for the folded-in fix).
- **Live smoke** (manual/script against a throwaway port): POST `/api/simulate` for the same
  domain with two different control overrides and confirm the target metric changes — proving
  each sweep run produces a distinct result through the real override path.
- **Adversarial review** of the diff before merge.
The value-generation and input-diff logic runs only in the browser and is not exercised by the
Python harness — the same constraint as the P2 and calibration UI work, called out honestly.

## Out of scope (YAGNI)

- A server-side `/api/sweep` endpoint (client loop was chosen).
- 2-D sweeps (varying two controls at once).
- Persisting scenarios across page reloads.
- Sweeping non-numeric / categorical variables.
- A fitness-based "winner" callout beyond the existing per-metric best/worst highlighting.

## Open questions

None — execution (client loop), value spec (min/max/step, cap 12), sweepable set (any slider),
replace-vs-append (replace), and input-diff scope (all differing) all resolved in brainstorming.

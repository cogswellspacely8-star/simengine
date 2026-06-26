# SimEngine — Product Analysis & Refinement Report

date: 2026-06-26

## Executive Summary

SimEngine's two most visible decision surfaces ship wrong numbers today, but the underlying simulation core is sound and every defect is fixable without touching the Monte Carlo math. The narrative headline reports a binary metric's median (which collapses to its mode) instead of its mean, so the BTC config reads "Pct Chance Above 70K is most likely 0.0" when the true probability is 32.4%. The evolutionary optimizer finds the winning lever values but discards them before they reach the API/MCP caller, making the optimum unactionable, and it mutates integer controls as continuous reals (recommending "1.5 baristas"). The chance-constraint evaluator only recognizes the literal token `"below"` and silently inverts every other keyword — including the `"lt"` used by four shipped Coffee Cart configs — turning a profitable plan into a false safety FAIL that also corrupts GA fitness. Two diagnostics (sensitivity OAT without common random numbers; deterministic baseline mishandling Bernoulli) have correctness siblings. None of these require changes to `_compute_stats_python` / `run_monte_carlo` — the kernel computes the right values; the bugs live in narrative selection, serialization, condition matching, and UI layout, all in `v3/` and all stdlib-only.

## Methodology

A black-box browser session surfaced a set of suspected issues; each was re-verified against the actual source in `/home/tony/projects/simengine/v3/`, and every claim below is anchored to a `file:line`. An independent correctness audit then read the surrounding code paths (kernel, diagnostics, validation, server, MCP, static UI) for sibling bugs not in the original report. Findings that could not be reproduced against source are recorded as refuted, not carried forward.

## Verification Summary

| ID | Title | Reported sev | Status | Assessed sev | Key location |
|----|-------|--------------|--------|--------------|--------------|
| audit-correctness | Chance-constraint keyword inversion; sensitivity OAT lacks CRN; deterministic Bernoulli baseline | high | confirmed | high | v3/kernel.py:520-523; v3/diagnostics.py:259,266,368-369 |
| safety-condition-lt | Chance-constraint else-branch inverts unknown condition keywords | high | confirmed | high | v3/kernel.py:520-525 |
| binary-metric-headline | Narrative headline reports median (mode) instead of mean for binary metrics | high | confirmed | high | v3/server.py:111-130, :128 |
| evolve-no-best-controls | Evolutionary optimizer never returns winning control settings | high | confirmed | high | v3/kernel.py:846-849; v3/server.py:530-537; v3/mcp_server.py:349-356 |
| evolve-continuous-integer-controls | Optimizer mutates integer controls as continuous (baristas=1.5) | high | confirmed | high | v3/kernel.py:715-725 |
| validation-accepts-malformed-tunable-fitness | validate_config never inspects tunable/fitness; malformed shape → opaque 500 | high | confirmed | high | v3/validation.py:104-167; v3/server.py:518-540 |
| results-render-offscreen | Results panel renders above the fold (dual scroll containers) | medium | confirmed | medium | v3/static/index.html:106,110,337-340 |
| minor-ux-cluster | Bare Fitness "0"; stray "Error" header; evolve lacks progress overlay (sensitivity claim refuted) | low | partially-confirmed | low | v3/static/index.html:1437,1351,1361-1388 |
| ask-hangs-freezes-page | Long /api/ask has no client AbortController/timeout/cancel ("freeze" refuted) | low | partially-confirmed | low | v3/static/index.html:2167-2203 |
| nl-pipeline-fragile-local-model | NL "Ask Anything" robustness with small local models | low | refuted | low | v3/llm/compiler.py:73-93 |

## Confirmed Defects (Prioritized)

### 1. Chance-constraint keyword inversion + sensitivity CRN + deterministic Bernoulli baseline (audit-correctness) — HIGH

**Root cause.** Three correctness defects in the math-adjacent paths. (a) `_evaluate_safety_python` matches only the literal `"below"` for less-than and treats every other condition as greater-than; four shipped Coffee Cart configs declare `"condition": "lt"` (intent `P(profit < 0)`), so the engine computes `P(profit > 0)` — the inverse — and that wrong verdict also feeds the 30% multiplicative GA fitness penalty in `compute_fitness`. (b) `sensitivity_analysis` central-difference uses *different* seeds for the up and down legs, so `up_mean - dn_mean` carries raw MC sampling noise instead of isolating the parameter effect. (c) `deterministic_baseline` plugs the Bernoulli mean `p` in as a fixed point estimate, producing a non-realizable fractional indicator.

**Location(s).**
- v3/kernel.py:520-523, :526
- v3/diagnostics.py:259, :266, :272, :368-369
- v3/schema/domain.schema.json:372
- v3/domains/Coffee_Cart___Staffing_Decision__Optimizable_.json

**Evidence.**
```python
# kernel.py:520-526
if cc["condition"] == "below":
    violations = sum(1 for v in vals if v < threshold)
else:
    violations = sum(1 for v in vals if v > threshold)
actual_prob = violations / len(vals)
```
Only `"below"` maps to `<`; `"lt"`, `"<"`, `"less_than"`, `"gt"`, `">="`, even a typo of `"above"`, collapse to `>`. Demonstrated: 20% of vals below zero with `condition:"lt", threshold:0` returns `actual_prob=0.8` (true `P(v<0)=0.2`) — a clean inversion.
```python
# diagnostics.py:259/266
r_up = run_monte_carlo(perturbed_up, seed=seed + trial * 2)
r_dn = run_monte_carlo(perturbed_dn, seed=seed + trial * 2 + 1)
impact = abs(up_mean - dn_mean) / 2
```
A zero-effect parameter registers spurious impact 0.06 with different seeds, exactly 0.0 with a shared seed.
```python
# diagnostics.py:368-369
elif dist == "bernoulli": point_est = params["p"]
```
A `hit*1000` payout with bernoulli `p=0.3` yields baseline payout 300 — an outcome that can never occur.

**Fix.** (a) kernel.py:520 — normalize: `cond = cc["condition"].lower(); below = cond in ("below","lt","<","less_than","lte","<=")`, branch on `below`; additively extend the schema enum. (b) diagnostics.py:259-266 — give both legs the same `trial_seed = seed + trial` (common random numbers). (c) diagnostics.py:368-369 — `point_est = 1.0 if params["p"] >= 0.5 else 0.0`.
Files: `v3/kernel.py`, `v3/diagnostics.py`, `v3/schema/domain.schema.json`. All stdlib-only; no port/Rust/JSON-shape changes (schema change is additive).
Risk: **Low-to-moderate.** Fixing the `lt` mapping *flips* the safety verdict for the four Coffee Cart domains (false violation → pass) and changes GA penalty trajectories — correct behavior, but golden-output snapshots must be regenerated; CRN lowers sensitivity numbers toward true effects so numeric assertions need updating.

**Test to add.** `v3/tests/test_safety_conditions.py`: assert `_evaluate_safety_python` returns the SAME `actual_prob` for `{"below","lt","<"}` and the complementary prob for `{"above","gt",">"}`; regression case `condition:"lt", threshold:0` asserting it counts `v<0`. A sensitivity test asserting a zero-effect variable scores `avg_impact_on_mean < epsilon` (fails today, passes after CRN). A `deterministic_baseline` test: bernoulli `p=0.3` driving `hit*1000` yields baseline `0.0` (mode), not 300.

---

### 2. Chance-constraint else-branch silently inverts unknown condition keywords (safety-condition-lt) — HIGH

**Root cause.** `_evaluate_safety_python` uses a single equality test (`if cc["condition"] == "below"`) with an unconditional `else`. Only the literal `"below"` counts `v < threshold`; every other value — including the schema-legal `"above"` and any alias/typo (`"lt"`, `"<"`, `"gt"`) — falls into the else and counts `v > threshold`. No runtime enum validation, no alias normalization. For a less-than intent expressed as `"lt"` against a near-all-positive profit metric (P10 = +$13,265, threshold 0), the else counts `v > 0` for ~100% of samples → `actual_prob = 1.0`, a false FAIL — the exact inverse of the true loss probability (~0%).

**Location(s).**
- /home/tony/projects/simengine/v3/kernel.py:520-525
- /home/tony/projects/simengine/v3/schema/domain.schema.json:370-374

**Evidence.**
```python
# kernel.py:520-525
if cc["condition"] == "below":
    violations = sum(1 for v in vals if v < threshold)
else:
    violations = sum(1 for v in vals if v > threshold)
actual_prob = violations / len(vals)
```
The `else` is a catch-all; `"lt"` therefore counts `v > threshold`. The schema (domain.schema.json:370-374) restricts `condition` to `["below","above"]` but the kernel performs no enum check at runtime, so an unvalidated config carrying `"lt"` is accepted and silently misevaluated. The schema description itself documents the foot-gun: "any other condition value counts v > threshold."

**Fix.** Replace the if/else with explicit alias normalization and a fail-loud guard:
```python
_CONDITION_BELOW = {"below", "lt", "<", "less_than"}
_CONDITION_ABOVE = {"above", "gt", ">", "greater_than"}
cond = str(cc["condition"]).strip().lower()
if cond in _CONDITION_BELOW:
    violations = sum(1 for v in vals if v < threshold)
elif cond in _CONDITION_ABOVE:
    violations = sum(1 for v in vals if v > threshold)
else:
    raise ValueError(f"Unknown chance-constraint condition {cc['condition']!r} for metric {metric!r}; expected one of below/lt/< or above/gt/>")
```
Widen the schema enum to `["below","lt","<","above","gt",">"]`. Files: `v3/kernel.py`, `v3/schema/domain.schema.json`.
Risk: **Low.** Existing configs use only `"below"`, which still maps correctly; the previously-silent `"above"` (routed via else to greater-than) remains correct under the alias map. The new raise fires only for genuinely unrecognized keywords that today produce wrong answers. Enum widening is a backward-compatible superset.

**Test to add.** In the SafetyEvaluation test class: `test_lt_alias_matches_below` (all-positive metric, threshold 0; assert `actual_prob == 0.0`, not 1.0); `test_above_condition_counts_greater_than` (assert 0.5 for a known split); `test_unknown_condition_raises` (assert `ValueError` for `"sideways"`). The first is the direct regression for the reported 100%-vs-0% inversion.

---

### 3. Narrative headline reports median (mode) instead of mean for binary/probability metrics (binary-metric-headline) — HIGH

**Root cause.** `generate_narrative()` builds the headline for every metric using `s['median']` unconditionally. A binary/indicator metric like the BTC config's `pct_chance_above_70k` (`"100 if price > 70000 else 0"`) produces per-run values of exactly 0 or 100; across runs the median of that indicator equals its mode, which (when the event is the ~32% minority) is 0. The *mean* of that same indicator IS the event probability (32.4). The kernel data is correct (mean and median both computed at kernel.py:483-484); only the narrative's choice of statistic is wrong. There is no `"type":"probability"` concept anywhere — the only display hint is `format` with enum `["number","dollar","percent"]`, and the BTC metric uses `"number"`, so nothing flags it as a probability.

**Location(s).**
- v3/server.py:111-130 (generate_narrative loop)
- v3/server.py:128 (the "is most likely {median_str}" headline)
- v3/server.py:114,118,122 (median_str from s['median'] in all three format branches)
- v3/kernel.py:483-484 (mean and median both computed; mean unused by narrative)
- v3/domains/btc_above_70k_jun2026.json:metrics.pct_chance_above_70k ("100 if price > 70000 else 0", format "number")
- v3/static/index.html:2239 (Export Report table column hardcoded to "Median")

**Evidence.**
```python
# server.py:111-130
for mname, s in stats.items():
    fmt = s.get("format", "number")
    if fmt == "dollar":   median_str = f"${s['median']:,.0f}" ...
    elif fmt == "percent": median_str = f"{s['median']*100:.1f}%" ...
    else:                  median_str = f"{s['median']:,.1f}" ...
    label = mname.replace("_", " ").title()
    lines.append(f"**{label}** is most likely {median_str} (range: {p10_str} to {p90_str} in 80% of scenarios).")
```
`s['mean']` (present per kernel.py:483) is never read. For `pct_chance_above_70k` the per-run values are in `{0,100}`; the median is 0 whenever fewer than half the runs exceed the threshold, so the headline says "most likely 0.0" even though mean=32.4 is the true probability — exactly reproducing the reported Median 0.00 / Mean 32.40 discrepancy.

**Fix.** Inside the per-metric loop, before the format branches, detect a binary indicator from fields already in `s`: treat as binary when `{s['p10'], s['median'], s['p90']}` is a subset of `{0,100}` or `{0,1}` with `std>0` and mean strictly between the extremes. When binary, emit a probability-style line reading `s['mean']` (e.g. `f"**{label}**: about {pct:.0f}% chance (mean of {n} scenarios)."`); otherwise fall through to the existing median phrasing unchanged. Single function, stdlib-only, no schema/kernel change. File: `v3/server.py`.
Risk: **Low.** Heuristic detection is guarded by `std>0` and mean-strictly-between; even a false positive falls back to a reasonable percentage reading. The Export Report table (index.html:2239) still shows Median for binary metrics, so table and headline can briefly disagree until a follow-up relabels that column — noted as a sibling, not part of this minimal fix.

**Test to add.** `v3/tests/test_narrative.py` importing `server.generate_narrative`. Build a stats dict for a binary metric concentrated at 0/100 with a minority event (`mean=32.4, median=0.0, p10=0, p90=100`); assert the narrative does NOT contain "most likely 0.0" and DOES surface ~32%. Add a non-binary companion (mean≠median, values not in {0,100}) asserting the existing median phrasing is preserved.

---

### 4. Evolutionary optimizer never returns the winning control settings (evolve-no-best-controls) — HIGH

**Root cause.** `evolve()` tracks the full winning genome as `best_ever`, and `best_ever["config"]` holds the optimized lever values at the tunable paths. But the return dict exposes only `best`, and both serializers deliberately project out fitness/stats/safety, dropping `config`. The optimum is found and reported numerically, yet the lever values that produced it are silently discarded before reaching the API/MCP caller — a serialization omission, not a kernel bug.

**Location(s).**
- v3/kernel.py:846-849 (return dict omits an extracted best_controls)
- v3/server.py:530-537 (/api/evolve response omits best_controls)
- v3/mcp_server.py:349-356 (handle_optimize result omits best_controls)
- v3/kernel.py:746 (_worker stores full config as best['config'])
- v3/kernel.py:800-801 (best_ever = deepcopy of winning scored entry)

**Evidence.** kernel.py:846-849 returns `{ "best": best_ever, "history": history, "manifest": manifest, "domain": config.name }` where `best_ever` carries the winning `config` (kernel.py:801). server.py:532-534 reads only `result["best"]["fitness"]`, `["stats"]`, `["safety"]` — never `["config"]`. mcp_server.py:351-353 is byte-for-byte the same projection. The tunable values live at `config[param.path]` (e.g. `"parameters.rate.params.mode"`), reachable via existing `_resolve_parent` helpers, but nothing reads them out.

**Fix.** In `evolve()` before the return, extract:
```python
best_controls = {}
if best_ever is not None:
    for spec in _prepare_tunable_specs(tunable):
        try:
            parent = _resolve_parent(best_ever["config"], spec["parents"])
            best_controls[spec["path"]] = parent[spec["leaf"]]
        except (KeyError, TypeError):
            pass
```
Return it under `"best_controls"`, then add `"best_controls": result["best_controls"],` to both server.py:530-537 and mcp_server.py:349-356. The CLI `main()` already dumps the whole result, so it gains the key transparently. Files: `v3/kernel.py`, `v3/server.py`, `v3/mcp_server.py`.
Risk: **Very low.** Additive key only — no existing key changes shape. `best_controls` is `{}` when there are no tunables; missing paths are skipped via try/except.

**Test to add.** In `TestEvolve`: run `kernel.evolve(MINI_CONFIG, generations=2, population=3, workers=1)` and assert `"best_controls" in result`, it is a dict, and contains `"parameters.rate.params.mode"` with a value inside `[0.1, 0.5]`. Optionally a serializer-level test asserting `handle_optimize(...)` and the `/api/evolve` response both include `best_controls`.

---

### 5. Optimizer mutates integer controls as continuous (recommends baristas=1.5) (evolve-continuous-integer-controls) — HIGH

**Root cause.** The optimizer mutates and crosses over every tunable as a continuous real. `mutate_config` writes `round(max(lo, min(hi, current + delta)), 4)` — the 4-dp round only kills float drift, not integrality. There is no integer/step concept anywhere: `_prepare_tunable_specs` records only `path` and `range`, and the schema's `tunable.items` allows only `path` and `range`. For the coffee-cart domain, `baristas` is a `fixed` distribution whose `_fixed` sampler returns `p["value"]` verbatim, and `capacity = baristas * cups_per_barista` evaluates a fractional barista count with no `int()` coercion. So evolve lands on baristas=1.5, which maximizes fitness ($17,814) because half a barista adds capacity without a full extra wage.

**Location(s).**
- v3/kernel.py:715-725 (mutate_config — continuous delta + round-to-4 only)
- v3/kernel.py:728-735 (crossover — copies raw float leaf, no coercion)
- v3/kernel.py:681-705 (_prepare_tunable_specs — spec carries only path+range)
- v3/kernel.py:36-37 (_fixed sampler returns p['value'] unrounded)
- v3/schema/domain.schema.json:138-154 (tunable item schema lacks integer/step)
- v3/domains/Coffee_Cart___Staffing_Decision__Optimizable_.json

**Evidence.**
```python
# kernel.py:715-725
def mutate_config(config_dict, tunable, rate=0.3, strength=0.15):
    new = copy.deepcopy(config_dict)
    for param in _prepare_tunable_specs(tunable):
        if random.random() > rate: continue
        lo, hi = param["range"]
        obj = _resolve_parent(new, param["parents"])
        current = obj[param["leaf"]]
        delta = random.gauss(0, (hi - lo) * strength)
        obj[param["leaf"]] = round(max(lo, min(hi, current + delta)), 4)  # 4-dp, NOT integer
    return new
```
The prepared spec has no integer flag (kernel.py:696-702), and `_fixed` returns the value as-is (kernel.py:36-37), so 1.5 reaches `capacity = baristas * cups_per_barista` and `labor = baristas * wage_per_day` unrounded — fractional capacity at fractional wage is why 1.5 wins the sweep.

**Fix.** Add an optional per-tunable `integer` (and optional numeric `step`) flag: read them in `_prepare_tunable_specs` (and include in the cache_key tuple), add a `_quantize(value, lo, hi, integer, step)` helper (clamp → snap to step → round to int if integer, else `round(...,4)`), and apply it in `mutate_config`'s final assignment. Add `"integer"`/`"step"` to `tunable.items.properties` (not required) and set `"integer": true` on the baristas tunable in the coffee-cart domain files. Files: `v3/kernel.py`, `v3/schema/domain.schema.json`, and the four `Coffee_Cart___Staffing*.json` domain files.
Risk: **Low.** Opt-in: configs without `integer`/`step` keep byte-identical continuous behavior. The cache_key must include the new flags to avoid collisions (addressed). Marking baristas integer slightly lowers the headline optimum vs the spurious 1.5 — the correct, decision-valid number.

**Test to add.** `test_mutate_config_respects_integer_flag`: tunable `{"path":"controls.baristas.params.value","range":[1,6],"integer":true}`, seed 0, call `mutate_config(... rate=1.0, strength=0.5)` ~50× and assert every result equals `int(v)` in `[1,6]`. `test_evolve_integer_control_never_fractional`: assert `result['best']['config']['controls']['baristas']['params']['value']` is integral. Negative control: same tunable WITHOUT the flag still produces a fractional value (locks backward compat).

---

### 6. validate_config never inspects tunable/fitness; malformed shape passes validation then crashes evolve with an opaque 500 (validation-accepts-malformed-tunable-fitness) — HIGH

**Root cause.** `validate_config()` validates name, n_steps, distributions, step_logic, metrics, and expression names — but has zero checks for the `tunable` and `fitness` blocks, which are consumed only by `evolve`. When `tunable` is an array of strings, `_prepare_tunable_specs` calls `param.get("path")` on a string and raises `AttributeError: 'str' object has no attribute 'get'`. The `/api/evolve` handler wraps the call in a bare `except Exception as e` returning a 500, so user-input error surfaces as an opaque 500 rather than a structured 4xx. Because `/api/validate` reports `valid:true`, the user cannot discover the malformed shape beforehand.

**Location(s).**
- /home/tony/projects/simengine/v3/validation.py:104-167 (validate_config — no tunable/fitness checks)
- /home/tony/projects/simengine/v3/kernel.py:681-705 (_prepare_tunable_specs: param.get('path'))
- /home/tony/projects/simengine/v3/kernel.py:656-657 (compute_fitness: comp['expr'] KeyError)
- /home/tony/projects/simengine/v3/server.py:518-540 (/api/evolve handler: bare except → 500)
- /home/tony/projects/simengine/v3/server.py:557-567 (/api/validate handler: trusts validate_config)

**Evidence.** Reproduced against source: with `tunable=['parameters.r.params.value']` and `fitness={'revenue':0.5,'safety':0.5}`, `validate_config(cfg)` returned `[]` (valid:true) and `kernel.evolve(cfg,...)` raised the exact reported `AttributeError`. Mechanism at kernel.py:681-688: `cache_key = tuple((param.get('path'), ...) for param in tunable)` — `param` is a str. server.py:538-539: `except Exception as e: self._json_response({"error": str(e)}, 500)`. `validation.py` contains no occurrence of 'tunable', 'fitness', or 'components' anywhere (104-167). Canonical shapes (domains/_template.json): `tunable=[{'path':...,'range':[lo,hi]}]`, `fitness={'components':[{'expr','weight','name'}]}`.

**Fix.** In `validate_config()`, after the metrics check, add stdlib structural checks: (1) if `tunable` present, require a list of dicts each with non-empty string `path` and a 2-element numeric `range` with `range[0] < range[1]` (specific per-item errors); (2) if `fitness` present and non-empty, require a `components` list of dicts each with a string `expr` (optional numeric `weight`), emitting `"fitness must use {'components': [...]}"` when ad-hoc weighted keys are detected. Separately, in `/api/evolve`, run `validate_config(data)` first and return 400 with `{'errors':[...]}` if non-empty; keep the 500 path only for genuinely unexpected errors. Files: `v3/validation.py`, `v3/server.py`.
Risk: **Low.** Could reject pre-existing on-disk configs with malformed tunable/fitness; mitigate by validating those blocks only when present and matching the canonical `_template.json` shape exactly. No schema/port/Rust changes.

**Test to add.** In `test_validation_robustness.py`: `test_tunable_array_of_strings_rejected` (set `config['tunable']=['parameters.r.params.value']`, assert non-empty errors mentioning 'tunable' and 'path'/'range'); `test_fitness_adhoc_weighted_keys_rejected` (`fitness={'revenue':0.5,'safety':0.5}`, assert error mentions 'components'); `test_fitness_component_missing_expr_rejected` (`fitness={'components':[{'weight':1.0}]}`, assert error mentions 'expr'). Optionally an API test asserting `/api/evolve` returns 400 (not 500).

---

### 7. Results panel renders above the fold because the tall sidebar drives document-level scroll (results-render-offscreen) — MEDIUM

**Root cause.** The desktop layout creates two independent scroll regions in a grid allowed to grow taller than the viewport. `.app` is `display:grid` with `min-height: calc(100vh - 45px)` and `body` is `min-height:100vh`, so the document scrolls. `.main` is hard-capped at `max-height: calc(100vh - 45px)` with its own `overflow-y:auto`, but `.sidebar` has `overflow-y:auto` with NO max-height and NO `min-height:0` at desktop width. On a grid, an auto-sized track ignores a child's `overflow:auto` unless height-constrained, so a tall sidebar stretches `.app` → `body`, producing document-level scroll. The height-capped `<main>` then sits in a band scrolled off-screen (observed top:-1252px), results present in the DOM. No code resets scroll: `runSimulation`/`renderResults` never call `scrollTo`/`scrollIntoView`. The authors capped the sidebar only under `@media max-width:900px` (line 1055), confirming desktop lacks the guard.

**Location(s).** v3/static/index.html:39, :103, :106, :110, :113, :337, :339, :340, :1325, :1488, :1055.

**Evidence.** Layout CSS 102-116 and 337-341 (sidebar `overflow-y:auto`, no max-height/`min-height:0` at desktop; main capped at `max-height: calc(100vh-45px)`); `body min-height:100vh` (39); `@media max-width:900px` caps sidebar at 50vh (1055), proving desktop lacks the guard; `runSimulation` success path (1344-1348) and `renderResults` innerHTML write (1488) contain no scroll reset.

**Fix.** (1) Change `.app` (106) from `min-height: calc(100vh - 45px)` to `height: calc(100vh - 45px)`, and add `min-height: 0` to both `.sidebar` (110) and `.main` (337) so their existing `overflow-y:auto` engages on the grid tracks — each column scrolls internally and the document no longer gains a viewport-spanning scrollbar. (2) After line 1488 in `renderResults` add `document.getElementById('main').scrollTop = 0;`. File: `v3/static/index.html`.
Risk: **Low.** The min-height→fixed-height + `min-height:0` pattern is the canonical fix for nested grid scroll containers; it changes scroll ownership, not visual layout. Modals use `position:fixed` so are unaffected. Verify the sidebar still scrolls to the Diagnostics buttons.

**Test to add.** Suite is stdlib-Python-only with no browser harness, so add a static-contract test `v3/tests/test_static_ui_layout.py` reading `index.html` as text: assert (a) `.app` uses `height: calc(100vh - 45px)` not `min-height`, (b) both `.sidebar` and `.main` blocks contain `min-height: 0`, (c) `renderResults` contains `scrollTop = 0`. Fails if the scroll-ownership fix is reverted, no runtime browser dependency.

---

### 8. Bare Fitness "0", stray "Error" header, evolve lacks progress overlay (minor-ux-cluster) — LOW (partially-confirmed)

**Root cause.** Three independent minor UI issues. (1) Bare Fitness 0: the server returns `fitness=0` whenever a config has no fitness block (server.py:492), and the UI unconditionally renders the "Fitness Score" gauge (index.html:1437), printing `r.fitness.toFixed(0) == "0"` with caption "Higher is better." — a meaningless 0 shown as a real score. (2) Stray "Error" header: `setStatus('Error')` (1351, 1383, 3010) writes into the persistent `#header-status` and nothing clears it; diagnostics paths use toasts and never call `setStatus`, so a stale "Error" can sit indefinitely. (3) Evolve has no progress overlay: `runEvolution` (1361) only swaps the button to a spinner, whereas convergence/sensitivity/baseline call `showLoading()`. The reporter's sensitivity-has-no-progress sub-claim is **refuted**: `runSensitivity` calls `showLoading` at index.html:3419.

**Location(s).** v3/static/index.html:1083, :1437, :1515-1531, :1524, :1528, :1351, :1383, :1361-1388, :3010, :3419; v3/server.py:492-494.

**Evidence.** Server: `fitness = 0` then `if cfg.fitness: fitness = compute_fitness(...)` (server.py:492-494). UI: `html += renderRiskSection(r);` (1437, unconditional) renders `${r.fitness.toFixed(0)}` (1524) with "Higher is better. Penalized for safety violations." (1528). `setStatus` (2001-2003) never auto-clears. `runEvolution` sets `Evolving...` + `setStatus('Running evolution...')` (1364-1365), no `showLoading`, vs `showLoading('Running sensitivity analysis', ...)` (3419).

**Fix.** (1) server.py: set `fitness = None` when `cfg.fitness` absent; render the Fitness card only when `r.fitness != null` (or a pure client-side guard `const hasFitness = !!(currentConfig && currentConfig.fitness && (currentConfig.fitness.components||[]).length)`). (2) After `setStatus('Error')` add a 4s `setTimeout` that resets to 'Ready' if still 'Error'. (3) Add `showLoading('Running evolution', ...)` at the top of `runEvolution` and `hideLoading()` in its finally. Leave `runSensitivity` untouched. Files: `v3/static/index.html`, `v3/server.py`.
Risk: **Very low; cosmetic.** `fitness=None` is isolated to the simulate-only gauge; optimize/evolve compute real fitness independently, so no numeric consumer breaks.

**Test to add.** Server-side: POST `/api/simulate` with a config lacking a `fitness` block and assert the response omits fitness / returns null (`assertIsNone(result.get('fitness'))`). UI behaviors (gauge suppression, header auto-clear, evolve overlay) stay outside the Python test surface — manual/visual check noted in the PR.

---

### 9. Long /api/ask has no client AbortController/timeout/cancel ("freezes whole page" refuted) (ask-hangs-freezes-page) — LOW (partially-confirmed)

**Root cause.** `runAsk` issues `await fetch('/api/ask', ...)` with no AbortController, no client timeout, and no cancel control. A slow local-LLM request leaves the modal in "Thinking…" for as long as the server takes, with no way to abort. The reported "freezes the whole page / tab unresponsive" is **NOT supported**: `runAsk` is `async` using `await fetch`, which yields the event loop; there is no synchronous XHR anywhere, and the modal overlay does not set `pointer-events:none`, so Close and the rest of the page stay interactive. Server-side the timeout IS enforced: `_default_post` calls `urlopen(req, timeout=timeout)` defaulting to `SIMENGINE_LLM_TIMEOUT` (120s). `answer_question` can make several bounded `complete()` calls, so total wall-clock can approach ~3.5 min — but each network wait is bounded and not main-thread-blocking.

**Location(s).** v3/static/index.html:2167-2203, :2180, :2124-2127; v3/llm/backends.py:54-72, :57-58; v3/server.py:182-194.

**Evidence.** Client (2177-2184): `await fetch('/api/ask', {...})` with no `signal:` option, no AbortController/timer; repo-wide grep for `AbortController|signal:|.abort(` in index.html returns nothing. Modal CSS (684-688) has no `pointer-events:none`; Close (`onclick="closeAsk()"`, 2125) stays active. Server timeout applied (backends.py:57-58,64): `if timeout is None: timeout = float(os.environ.get("SIMENGINE_LLM_TIMEOUT","120"))` ... `with urllib.request.urlopen(req, timeout=timeout) as resp:`.

**Fix.** In `runAsk()`: `const ctrl = new AbortController();` passed as `signal: ctrl.signal`; a client cap `const tid = setTimeout(() => ctrl.abort(), 240000)` cleared in finally; while in flight swap the run button to a Cancel that calls `ctrl.abort()`; catch `AbortError` (`e.name === 'AbortError'`) and render "Request cancelled / timed out — try a smaller/faster model or fewer runs." No server change. File: `v3/static/index.html`.
Risk: **Very low.** Confined to one JS function plus a button handler; only risk is mislabeling AbortError vs network error in the catch (handle via `e.name`).

**Test to add.** Python unit test in `test_llm_backends.py` monkeypatching `urllib.request.urlopen` to record the `timeout` kwarg: set `SIMENGINE_LLM_TIMEOUT='7'`, call `backends._default_post(url, {}, {})`, assert recorded timeout `== 7.0` (and 120.0 when unset). The client AbortController is untestable without a JS runner — document as manual QA.

## Refuted / Inconclusive

- **nl-pipeline-fragile-local-model (refuted).** The observed behavior is the pipeline working as designed, not a defect. A 7B model emitted an invalid `step_logic` entry; SimEngine's validator caught it (`validation.py:145-146`, "missing 'expr' or 'sample'") and the compiler's repair loop fed the exact error back and retried (`compiler.py:73-93`). All four questioned mechanisms are present and correct: two valid few-shot configs in `SYSTEM_PROMPT` (prompts.py:13-54, 97-98); validator errors + available names fed into each repair round (compiler.py:88-91); the generated config surfaced to the user (web details, CLI `--show-config`, JSON); `max_repairs=3` → 4 attempts. The residual "poor success rate" is an inherent small-local-model limitation. Genuine minor gaps remain: the `sample` step form is documented (prompts.py:71) but never demonstrated in a few-shot, and the UI shows the config read-only (index.html:2243-2248) with no edit-and-rerun, so a user cannot rescue a config the model can't repair. Optional hardening only.
- **"Page freeze" sub-claim (refuted)** within ask-hangs-freezes-page — see Defect 9; the async/await flow does not block the main thread and the modal stays interactive.
- **"Sensitivity has no progress overlay" sub-claim (refuted)** within minor-ux-cluster — `runSensitivity` calls `showLoading` at index.html:3419.

## Additional Findings from the Correctness Audit

Sibling bugs surfaced while verifying the above (deduped; the chance-constraint and sensitivity/Bernoulli items are the primary confirmed defects 1–2 and are not repeated here).

| Finding | Location | Severity |
|---------|----------|----------|
| `sim_ask.py` CLI printer has the SAME median-as-mode defect as the narrative (prints `median {value}` with no binary detection) | v3/sim_ask.py:46-48 | high |
| Export Report table header hardcoded to "Median"; binary metrics show Median 0.00 instead of the probability | v3/static/index.html:2239 | medium |
| Native (Rust) path swallows ALL exceptions with bare `except Exception: pass`, masking divergent/buggy native results | v3/kernel.py:637-640 | medium |
| `compute_fitness` with ad-hoc weighted-keys fitness silently evaluates to 0.0 (optimizer ranks everything at 0) — silent wrong result | v3/kernel.py:656-658 | medium |
| `compute_fitness` component missing `expr` raises `KeyError('expr')` → unguarded 500 via `/api/evolve` | v3/kernel.py:657 | medium |
| `_student_t` does `range(df)`; non-integer `df` (e.g. 4.5) raises `TypeError` surfaced only as vague "Test run failed" | v3/kernel.py:67-70 | low |
| Schema enums (`format`, `condition`) have drifted from shipped domains using `currency` and `lt`; `test_schema_contract` fails today | v3/schema/domain.schema.json:356,372 | medium |
| `deterministic_baseline` handles `dist=='choice'` but `choice` is not a registered sampler — dead/inconsistent branch | v3/diagnostics.py:340-375 | low |
| Chance-constraint keys accessed via direct subscript (no `.get`); malformed config raises raw `KeyError` mid-evaluation | v3/kernel.py:512-518 | low |
| `if not vals: continue` silently drops a constraint when the metric is absent/empty; a typo'd metric name passes safety vacuously | v3/kernel.py:514 | medium |
| `top_metric = list(best['stats'].keys())[0]` assumes non-empty ordered dict; empty-metrics config IndexErrors during verbose evolve | v3/kernel.py:807 | low |
| `best_ever` could be None if population evaluation yielded nothing; `best_ever['fitness']` defensive None-guard absent | v3/kernel.py:835 | low |
| Mutation noise scales with full `(hi-lo)` range; for `[1,6]` integer control `strength=0.25` gives sigma=1.25, biasing toward boundary/fractional values | v3/kernel.py:723 | low |
| `crossover` does not re-clamp/quantize; safe only because parents are pre-quantized — a hand-authored fractional/out-of-range seed propagates until first mutation | v3/kernel.py:728-735 | low |
| `_worker` caps n at `min(cfg.n_simulations, 2000)` during evolution; evolve fitness uses fewer sims than a standalone run (evaluation-noise) | v3/kernel.py:741 | low |
| `/api/evolve` only supports file-based domains (`load_domain(body.get('domain'))`) and ignores inline `body['config']`, unlike `/api/simulate` | v3/server.py:524 | low |
| Evolve handler swallows all exceptions into a generic 500 with raw `str(e)`, no traceback logging (unlike `/api/simulate`) | v3/server.py:538-539 | low |
| Error paths overwrite `#main` innerHTML and also never reset scroll, so an error after a long result can render off-screen too | v3/static/index.html:1350,1382,3010 | low |
| Six sites write `#main` innerHTML directly; centralize scroll-reset in a `setMain(html)` helper to avoid re-introducing the off-screen bug | v3/static/index.html:1488,1906,3028,3276,3440,3519 | low |
| Hard-coded 45px header offset in `calc(100vh - 45px)` is an assumption; real header height can differ, causing minor layout drift | v3/static/index.html:106,340 | low |
| Fitness gauge uses `Math.min(r.fitness,100)/100`, so fitness >100 saturates the ring while the numeric label exceeds it | v3/static/index.html:1522,1524 | low |
| `runSensitivity` picks metric via `Object.keys(currentResults.stats)[0]`; chosen metric is implicit/unlabeled and key order is engine-dependent | v3/static/index.html:3422 | low |
| Three near-duplicate error-render blocks (main empty-state + `setStatus('Error')`) are copy-pasted; inconsistent error UX | v3/static/index.html:1351,1383,3010 | low |
| `_default_get` (model listing) shares the 120s `SIMENGINE_LLM_TIMEOUT`; `loadAskModels` can wait up to 120s with no client abort | v3/llm/backends.py:75-80 | low |
| `handle_ask` can trigger multiple sequential `complete()` calls each bounded by the per-call timeout; no overall request budget | v3/server.py:182-194 | low |
| Ask hint says local models "can take 30-90s" but communicates no upper bound, reinforcing the perceived hang | v3/static/index.html:2178,2112 | low |
| `mcp_server.py` carries a near-identical duplicate validator; drift risk if one is updated without the other | v3/validation.py:9-10 | low |
| `saveAskDomain` reads `data.file` for the success toast; confirm the save-domain response returns `file` (vs `saved_name`) or the toast shows 'undefined' | v3/static/index.html:2261 | low |
| The `sample` step form is documented in schema text but absent from both few-shot examples, unmodeled for small models | v3/llm/prompts.py:71 | low |
| `diagnostics.py:357` also extracts a "most likely" value for deterministic forecasts; check it doesn't propagate the same median-as-mode confusion for binary accumulators | v3/diagnostics.py:357 | low |
| No schema-level way to declare a metric as probability/binary (`format` enum is number/dollar/percent only) — a `"probability"` opt-in would let authors flag indicators explicitly | v3/schema/domain.schema.json:353-357 | low |

## What Works Well — Keep & Build On

| Surface | Why it's sound |
|---------|----------------|
| Monte Carlo core (`run_monte_carlo`, `_compute_stats_python`) | Mean/median/p10/p90 are all computed correctly (kernel.py:483-484); every wrong-number bug is in a downstream selection/serialization layer, not the math. |
| Diagnostics suite (sensitivity, convergence, baseline) | Already wired into the UI with progress overlays (showLoading at 3419/3255/3496); sensitivity and baseline need the CRN/Bernoulli fixes but the framing and UX are right. |
| Export Report | Structured tabular export already exists; only needs the Median→Mean/Chance relabel for binary metrics. |
| NL "Ask Anything" compile/repair loop | Validator-driven repair with error feedback, few-shot examples, surfaced config, and bounded retries (compiler.py:73-93) — robust by design; the only ceiling is small-model reliability. |
| Brier-scored Predictions / calibration ledger | Real calibration accounting is a differentiating, trust-building surface to lean into. |

## Refinement Roadmap

**P1 — Trust fixes (the wrong-number bugs).** Defects 1–6: chance-constraint keyword normalization + fail-loud guard, sensitivity CRN, Bernoulli mode baseline, binary-metric narrative mean (+ the `sim_ask.py` sibling and the Export Report column), `best_controls` serialization, integer-control quantization, and tunable/fitness validation with 4xx. *Rationale: these produce confidently-wrong decision outputs on flagship surfaces and must be corrected before any feature work; all are stdlib-only and contained in `v3/`.*

**P2 — UX & reliability.** Defect 7 (grid scroll ownership + scroll reset), Defect 9 (ask AbortController/timeout/cancel), Defect 8 (fitness gauge suppression, header auto-clear, evolve progress overlay), and centralizing `#main` writes through a `setMain()` helper. *Rationale: these don't corrupt numbers but make correct results hard to see or trust, and a results panel rendering above the fold reads as "nothing happened."*

**P3 — Build-on.** Lean into the Brier-scored calibration ledger as the product's trust differentiator; harden the NL pipeline (add the `sample` few-shot example, make the web config editable with re-validate/re-run); add scenario comparison; build a template gallery seeded from the existing domain library. *Rationale: with the engine proven correct and legible, these compound the decision-intelligence positioning rather than patching defects.*

## Issue-Ready Entries

**Chance-constraint keyword matching inverts violation probability (`lt` → false FAIL)**
labels: `bug`, `severity:high`, `area:kernel`
Repro: load any Coffee Cart domain with `"condition":"lt"` against `total_profit` (threshold 0) on a near-all-positive distribution; observe a false safety FAIL (actual_prob≈1.0) when true P(profit<0)≈0.
Root cause: v3/kernel.py:520-525 — `if cc["condition"] == "below" ... else (v > threshold)`; unknown keywords fall through to greater-than. Schema enum `["below","above"]` not runtime-enforced (domain.schema.json:370-374).
Acceptance: `lt/below/<` count `v < threshold`; `gt/above/>` count `v > threshold`; unknown keyword raises `ValueError`; schema enum widened; four Coffee Cart domains report a pass; new `test_safety_conditions.py` passes.

**Sensitivity OAT lacks common random numbers**
labels: `bug`, `severity:medium`, `area:diagnostics`
Repro: run `sensitivity_analysis` on a config with a variable that has zero effect on the metric; observe a spurious nonzero impact (~0.06).
Root cause: v3/diagnostics.py:259,266 — up/down legs use different seeds (`seed+2*trial` vs `+1`).
Acceptance: both legs share `trial_seed = seed + trial`; a zero-effect variable scores `avg_impact_on_mean < epsilon`.

**Deterministic baseline mishandles Bernoulli**
labels: `bug`, `severity:medium`, `area:diagnostics`
Repro: `deterministic_baseline` on a `hit*1000` payout with bernoulli `p=0.3` yields baseline payout 300 (non-realizable).
Root cause: v3/diagnostics.py:368-369 — `point_est = params["p"]` (mean) instead of mode.
Acceptance: `point_est = 1.0 if p >= 0.5 else 0.0`; the example yields baseline 0.0.

**Narrative headline reports median (mode) instead of mean for binary metrics**
labels: `bug`, `severity:high`, `area:server`
Repro: simulate `btc_above_70k_jun2026`; headline reads "Pct Chance Above 70K is most likely 0.0" while mean=32.4.
Root cause: v3/server.py:111-130, :128 — `s['median']` used unconditionally; `s['mean']` (kernel.py:483) unused.
Acceptance: binary/indicator metrics ({0,100} or {0,1}, std>0) report the mean as a probability; non-binary metrics keep median phrasing; `test_narrative.py` passes; apply the same fix to sim_ask.py:46-48.

**Evolutionary optimizer never returns winning control settings**
labels: `bug`, `severity:high`, `area:kernel`, `area:api`
Repro: run `/api/evolve` (or MCP `handle_optimize`) on an optimizable domain; response has best_fitness/stats/safety but no lever values.
Root cause: v3/kernel.py:846-849 return omits controls; server.py:530-537 and mcp_server.py:349-356 project them out.
Acceptance: `evolve()` returns `best_controls` ({path: value}); both serializers include it; `test_evolve` asserts the tunable path key with an in-range value.

**Optimizer mutates integer controls as continuous (baristas=1.5)**
labels: `bug`, `severity:high`, `area:kernel`
Repro: run evolve on a Coffee Cart optimizable domain; best config returns `baristas=1.5`.
Root cause: v3/kernel.py:715-725 — `round(...,4)` only; no integer/step concept (specs at 681-705, schema at 138-154).
Acceptance: opt-in `integer`/`step` per tunable; quantized in `mutate_config`; baristas tunable marked integer; mutated/evolved baristas always integral in `[1,6]`; configs without the flag keep continuous behavior.

**validate_config never inspects tunable/fitness (malformed shape → opaque 500)**
labels: `bug`, `severity:high`, `area:validation`, `area:api`
Repro: POST a domain with `tunable=['parameters.r.params.value']` to `/api/validate` (returns valid:true) then `/api/evolve` (returns HTTP 500 `'str' object has no attribute 'get'`).
Root cause: v3/validation.py:104-167 (no tunable/fitness checks); v3/server.py:518-540 (bare except → 500).
Acceptance: `validate_config` rejects non-canonical tunable/fitness with specific messages; `/api/evolve` returns 400 with `{'errors':[...]}` for malformed input; new tests in `test_validation_robustness.py` pass.

**Results panel renders above the fold (dual scroll containers)**
labels: `bug`, `severity:medium`, `area:ui`
Repro: on a desktop viewport, run a simulation with a tall sidebar; results render off-screen (main top ≈ -1252px) until a manual scroll-to-top.
Root cause: v3/static/index.html:106,110,337-340 — `.app min-height` grows the document; `.sidebar` lacks max-height/`min-height:0` at desktop; no scroll reset in renderResults.
Acceptance: `.app` uses fixed `height: calc(100vh - 45px)`; `.sidebar` and `.main` have `min-height:0`; `renderResults` resets `scrollTop = 0`; `test_static_ui_layout.py` asserts the guards.

**Long /api/ask has no client AbortController/timeout/cancel**
labels: `bug`, `severity:low`, `area:ui`
Repro: ask a question against a slow local model; modal stays "Thinking…" with no way to cancel (note: page does NOT freeze).
Root cause: v3/static/index.html:2167-2203, :2180 — `await fetch('/api/ask')` with no `signal`, timer, or cancel.
Acceptance: AbortController with a client cap (~240s) and a Cancel button; AbortError renders a friendly cancel/timeout message; server `SIMENGINE_LLM_TIMEOUT` pass-through locked by a `test_llm_backends.py` test.

**Minor UX cluster: bare Fitness "0", stray "Error" header, evolve progress overlay**
labels: `bug`, `severity:low`, `area:ui`, `area:server`
Repro: simulate a config with no fitness block (gauge shows "0"); trigger an error (header stuck on "Error"); run evolve (no progress overlay).
Root cause: v3/server.py:492-494 (`fitness=0` when none); v3/static/index.html:1437 (gauge always rendered), :1351/1383/3010 (`setStatus('Error')` never cleared), :1361-1388 (no `showLoading`).
Acceptance: no-objective configs return null fitness / suppress the gauge; "Error" auto-clears to "Ready" after ~4s; `runEvolution` shows a `showLoading` overlay; `runSensitivity` left unchanged.

## Regression Fixture

Use the **coffee-cart staffing table** as a canonical regression check for the optimizer and safety stack. The correct decision is **2 baristas** (the integer staffing level that maximizes profit while keeping the loss probability within the chance constraint). Any optimizer run that returns **1.5 baristas** (continuous-control bug, Defect 5), that **hides the winning lever value** (serialization bug, Defect 4), or that reports the **profitable plan as a safety violation** because `"lt"` inverts to `>` (Defect 1/2) is still broken. The fixture should assert: (a) `best_controls['controls.baristas.params.value']` is integral and equals 2; (b) the `"condition":"lt"` profit constraint reports a **pass**, not a FAIL; (c) `best_controls` is present and non-empty in both the `/api/evolve` and MCP `handle_optimize` outputs.
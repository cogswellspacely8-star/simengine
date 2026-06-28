# Calibration Ledger — Capture + Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users one-click "Track this forecast" from binary-indicator simulations/Ask answers into the existing calibration ledger, and surface a gated reliability diagram so the track record's calibration becomes visible.

**Architecture:** Reliability math is added to `v3/calibration.py` (pure stdlib, unit-tested next to the existing Brier/log-loss). The diagram renders on a `<canvas>` in the single-file UI, following the existing histogram/trajectory pattern. Capture reuses the existing `/api/forecast` endpoint and the existing `forecasts` table columns (`metric`, `resolve_by`) — no DB migration; `/api/forecasts` is extended with a `calibration` key.

**Tech Stack:** Python 3.8+ stdlib (`sqlite3`, `math`, `statistics`), `unittest`; vanilla HTML/JS/CSS single file; `jsonschema` (test-only, optional).

## Global Constraints

- Pure Python stdlib only in `v3/*.py` — no new pip dependencies, no `requirements.txt` entries.
- Keep default port 8420. Pure-Python path must work without the Rust extension.
- Do NOT break the JSON config schema; schema additions must be additive (optional, not `required`).
- Do NOT move production code out of `v3/`. The UI stays a single file (`v3/static/index.html`), no build step.
- `MIN_RESOLVED_FOR_CURVE = 10` (the reliability-diagram gate threshold) — exact value.
- Reliability bins: 10 equal-width buckets `[0,0.1) … [0.9,1.0]`, last bucket includes 1.0.
- Run the suite with `make test` (or `python3 -m unittest discover -s v3/tests -p 'test_*.py'`). Use `python3 -B` when checking a single new test to avoid stale `.pyc`.
- End every commit message with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Branch: `feat/calibration-ledger`.

## File Structure

- `v3/calibration.py` — MODIFY: add `reliability_curve`, `expected_calibration_error`, `calibration_report` methods + `MIN_RESOLVED_FOR_CURVE` constant. Existing `score()` untouched.
- `v3/server.py` — MODIFY: `handle_forecasts_list()` adds a `calibration` key.
- `v3/schema/domain.schema.json` — MODIFY: add optional top-level `resolve_by` string property.
- `v3/static/index.html` — MODIFY: Track-forecast button + modal (capture), reliability diagram + gate in the Predictions modal (viz).
- `v3/tests/test_calibration.py` — MODIFY: reliability/ECE/report + metadata round-trip tests.
- `v3/tests/test_api_forecast.py` — MODIFY: `/api/forecasts` calibration-shape test.
- `v3/tests/test_schema_contract.py` — MODIFY: `resolve_by` accepted.
- `v3/tests/test_calibration_ui.py` — CREATE: static-contract guards for the new UI.

---

### Task 1: `reliability_curve` on `CalibrationLedger`

**Files:**
- Modify: `v3/calibration.py` (add method to `CalibrationLedger`)
- Test: `v3/tests/test_calibration.py`

**Interfaces:**
- Consumes: existing `CalibrationLedger.record(question, predicted_prob, *, resolve_by=None, metric=None)`, `resolve(id, outcome)`, `resolved()` (returns list of dicts with keys including `predicted_prob`, `outcome`).
- Produces: `CalibrationLedger.reliability_curve(n_bins=10) -> list[dict]`, each dict `{"lo","hi","count","mean_predicted","observed_freq"}` for non-empty bins, ordered low→high; `[]` when nothing is resolved.

- [ ] **Step 1: Write the failing test**

```python
# in v3/tests/test_calibration.py
from calibration import CalibrationLedger  # adjust to existing import style in the file

class TestReliabilityCurve(unittest.TestCase):
    def _ledger(self, pairs):
        led = CalibrationLedger(":memory:")
        for p, o in pairs:
            fid = led.record("q", p)
            led.resolve(fid, o)
        return led

    def test_two_extreme_bins(self):
        led = self._ledger([(0.05, 0), (0.05, 0), (0.95, 1), (0.95, 1)])
        curve = led.reliability_curve()
        self.assertEqual(len(curve), 2)
        lo, hi = curve[0], curve[1]
        self.assertEqual((lo["lo"], lo["hi"], lo["count"]), (0.0, 0.1, 2))
        self.assertAlmostEqual(lo["mean_predicted"], 0.05)
        self.assertAlmostEqual(lo["observed_freq"], 0.0)
        self.assertEqual((hi["lo"], hi["hi"], hi["count"]), (0.9, 1.0, 2))
        self.assertAlmostEqual(hi["observed_freq"], 1.0)

    def test_prob_one_lands_in_last_bin(self):
        led = self._ledger([(1.0, 1)])
        curve = led.reliability_curve()
        self.assertEqual(len(curve), 1)
        self.assertEqual(curve[0]["lo"], 0.9)

    def test_empty_when_nothing_resolved(self):
        self.assertEqual(CalibrationLedger(":memory:").reliability_curve(), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration.TestReliabilityCurve -v`
Expected: FAIL — `AttributeError: 'CalibrationLedger' object has no attribute 'reliability_curve'`

- [ ] **Step 3: Write minimal implementation**

```python
# method on CalibrationLedger in v3/calibration.py
def reliability_curve(self, n_bins=10):
    """Per-bucket calibration points over resolved forecasts.

    Predicted probabilities are binned into n_bins equal-width buckets
    [0,1/n), ... [1-1/n, 1] (the last bucket includes 1.0). Each non-empty
    bucket reports its count, mean predicted probability, and observed
    outcome frequency. Empty buckets are omitted.
    """
    rows = self.resolved()
    if not rows:
        return []
    width = 1.0 / n_bins
    buckets = [[] for _ in range(n_bins)]
    for r in rows:
        p = r["predicted_prob"]
        idx = min(int(p / width), n_bins - 1)
        buckets[idx].append((p, r["outcome"]))
    curve = []
    for i, b in enumerate(buckets):
        if not b:
            continue
        ps = [p for p, _ in b]
        outs = [o for _, o in b]
        curve.append({
            "lo": round(i * width, 4),
            "hi": round((i + 1) * width, 4),
            "count": len(b),
            "mean_predicted": round(sum(ps) / len(ps), 4),
            "observed_freq": round(sum(outs) / len(outs), 4),
        })
    return curve
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration.TestReliabilityCurve -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add v3/calibration.py v3/tests/test_calibration.py
git commit -m "feat(calibration): reliability_curve over resolved forecasts"
```

---

### Task 2: `expected_calibration_error`

**Files:**
- Modify: `v3/calibration.py`
- Test: `v3/tests/test_calibration.py`

**Interfaces:**
- Consumes: `reliability_curve(n_bins)` from Task 1.
- Produces: `CalibrationLedger.expected_calibration_error(n_bins=10) -> float | None` (count-weighted mean of `|observed_freq - mean_predicted|`; `None` when nothing resolved).

- [ ] **Step 1: Write the failing test**

```python
# in v3/tests/test_calibration.py (reuse the _ledger helper or duplicate it)
class TestECE(unittest.TestCase):
    def _ledger(self, pairs):
        led = CalibrationLedger(":memory:")
        for p, o in pairs:
            led.resolve(led.record("q", p), o)
        return led

    def test_perfect_calibration_is_zero(self):
        led = self._ledger([(0.0, 0), (1.0, 1)])
        self.assertEqual(led.expected_calibration_error(), 0.0)

    def test_known_value(self):
        # bin0: pred 0.05 obs 0.0 -> |0.05|; bin9: pred 0.95 obs 1.0 -> |0.05|
        led = self._ledger([(0.05, 0), (0.05, 0), (0.95, 1), (0.95, 1)])
        self.assertAlmostEqual(led.expected_calibration_error(), 0.05)

    def test_none_when_empty(self):
        self.assertIsNone(CalibrationLedger(":memory:").expected_calibration_error())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration.TestECE -v`
Expected: FAIL — `AttributeError: ... 'expected_calibration_error'`

- [ ] **Step 3: Write minimal implementation**

```python
# method on CalibrationLedger in v3/calibration.py
def expected_calibration_error(self, n_bins=10):
    """Count-weighted mean gap between predicted and observed per bucket.

    ECE = Σ_bins (count / N) · |observed_freq − mean_predicted|. None when
    no forecasts are resolved.
    """
    curve = self.reliability_curve(n_bins)
    if not curve:
        return None
    total = sum(b["count"] for b in curve)
    return round(
        sum(b["count"] / total * abs(b["observed_freq"] - b["mean_predicted"])
            for b in curve),
        4,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration.TestECE -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add v3/calibration.py v3/tests/test_calibration.py
git commit -m "feat(calibration): expected_calibration_error"
```

---

### Task 3: `calibration_report` (gated) + `MIN_RESOLVED_FOR_CURVE`

**Files:**
- Modify: `v3/calibration.py`
- Test: `v3/tests/test_calibration.py`

**Interfaces:**
- Consumes: module functions `brier_score`, `log_loss` (already in `calibration.py`); `reliability_curve`, `expected_calibration_error`.
- Produces: module constant `MIN_RESOLVED_FOR_CURVE = 10`; `CalibrationLedger.calibration_report(min_n=MIN_RESOLVED_FOR_CURVE, n_bins=10) -> dict` with keys `{"n","brier","log_loss","base_rate","ready","min_n","curve","ece"}`. `curve`/`ece` are `None` unless `n >= min_n`; everything `None` (except `n=0, ready=False`) when nothing resolved.

- [ ] **Step 1: Write the failing test**

```python
# in v3/tests/test_calibration.py
import calibration as cal_mod

class TestCalibrationReport(unittest.TestCase):
    def _ledger(self, pairs):
        led = CalibrationLedger(":memory:")
        for p, o in pairs:
            led.resolve(led.record("q", p), o)
        return led

    def test_empty(self):
        rep = CalibrationLedger(":memory:").calibration_report()
        self.assertEqual(rep["n"], 0)
        self.assertFalse(rep["ready"])
        self.assertIsNone(rep["curve"])
        self.assertIsNone(rep["ece"])
        self.assertEqual(rep["min_n"], cal_mod.MIN_RESOLVED_FOR_CURVE)

    def test_below_threshold_not_ready(self):
        rep = self._ledger([(0.5, 1), (0.5, 0)]).calibration_report()
        self.assertEqual(rep["n"], 2)
        self.assertFalse(rep["ready"])
        self.assertIsNone(rep["curve"])
        self.assertIsNotNone(rep["brier"])          # score still computed
        self.assertAlmostEqual(rep["base_rate"], 0.5)

    def test_at_threshold_ready_with_curve(self):
        rep = self._ledger([(0.9, 1)] * 10).calibration_report()
        self.assertEqual(rep["n"], 10)
        self.assertTrue(rep["ready"])
        self.assertTrue(rep["curve"])               # non-empty list
        self.assertIsNotNone(rep["ece"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration.TestCalibrationReport -v`
Expected: FAIL — `AttributeError: ... 'calibration_report'` (and `MIN_RESOLVED_FOR_CURVE` missing)

- [ ] **Step 3: Write minimal implementation**

```python
# near the top of v3/calibration.py, after the scoring functions
MIN_RESOLVED_FOR_CURVE = 10

# method on CalibrationLedger
def calibration_report(self, min_n=MIN_RESOLVED_FOR_CURVE, n_bins=10):
    """Aggregate scores + a gated reliability curve.

    Returns brier/log-loss/base-rate over all resolved forecasts, plus the
    reliability curve and ECE ONLY when at least `min_n` are resolved (a curve
    over a handful of points would imply a track record that doesn't exist).
    """
    rows = self.resolved()
    n = len(rows)
    if n == 0:
        return {"n": 0, "brier": None, "log_loss": None, "base_rate": None,
                "ready": False, "min_n": min_n, "curve": None, "ece": None}
    preds = [r["predicted_prob"] for r in rows]
    outs = [r["outcome"] for r in rows]
    ready = n >= min_n
    return {
        "n": n,
        "brier": round(brier_score(preds, outs), 4),
        "log_loss": round(log_loss(preds, outs), 4),
        "base_rate": round(sum(outs) / n, 4),
        "ready": ready,
        "min_n": min_n,
        "curve": self.reliability_curve(n_bins) if ready else None,
        "ece": self.expected_calibration_error(n_bins) if ready else None,
    }
```

Note: `brier_score` and `log_loss` are module-level functions already defined in `calibration.py`; call them directly (as `score()` does).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration.TestCalibrationReport -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add v3/calibration.py v3/tests/test_calibration.py
git commit -m "feat(calibration): gated calibration_report + MIN_RESOLVED_FOR_CURVE"
```

---

### Task 4: `/api/forecasts` returns `calibration` + metadata round-trip guard

**Files:**
- Modify: `v3/server.py:259-262` (`handle_forecasts_list`)
- Test: `v3/tests/test_api_forecast.py`

**Interfaces:**
- Consumes: `CalibrationLedger.calibration_report()` (Task 3); existing `_ledger()` (reads `SIMENGINE_LEDGER_DB`).
- Produces: `handle_forecasts_list() -> ({"forecasts","score","calibration"}, 200)`.

- [ ] **Step 1: Write the failing test**

```python
# in v3/tests/test_api_forecast.py (match the file's existing tmp-ledger pattern)
def test_forecasts_list_includes_calibration(self):
    # self.tmpdb / env setup mirrors existing tests in this file
    server.handle_forecast_record({"question": "q", "predicted_prob": 0.6,
                                   "metric": "pct_chance", "resolve_by": "2026-12-31"})
    payload, status = server.handle_forecasts_list()
    self.assertEqual(status, 200)
    self.assertIn("calibration", payload)
    cal = payload["calibration"]
    self.assertIn("ready", cal)
    self.assertIn("min_n", cal)
    # the logged forecast kept its metric + resolve_by
    f = payload["forecasts"][-1]
    self.assertEqual(f["metric"], "pct_chance")
    self.assertEqual(f["resolve_by"], "2026-12-31")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd v3 && python3 -B -m unittest tests.test_api_forecast -v`
Expected: FAIL — `KeyError: 'calibration'` / `'calibration' not found`

- [ ] **Step 3: Write minimal implementation**

```python
# v3/server.py — handle_forecasts_list
def handle_forecasts_list():
    """All logged forecasts (pending + resolved) plus running scores and the
    gated calibration report."""
    led = _ledger()
    return {"forecasts": led.all_forecasts(), "score": led.score(),
            "calibration": led.calibration_report()}, 200
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd v3 && python3 -B -m unittest tests.test_api_forecast -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add v3/server.py v3/tests/test_api_forecast.py
git commit -m "feat(api): include gated calibration report in /api/forecasts"
```

---

### Task 5: Optional `resolve_by` domain schema field

**Files:**
- Modify: `v3/schema/domain.schema.json` (top-level `properties`)
- Test: `v3/tests/test_schema_contract.py`

**Interfaces:**
- Produces: schema accepts an optional top-level `"resolve_by"` (ISO date string). Not in `required`.

- [ ] **Step 1: Write the failing test**

```python
# in v3/tests/test_schema_contract.py, inside TestSchemaContract
def test_accepts_optional_resolve_by(self):
    cfg = {"name": "x", "n_steps": 5, "resolve_by": "2026-06-30",
           "parameters": {"p": {"distribution": "fixed", "params": {"value": 1}}},
           "step_logic": [{"target": "y", "expr": "p"}],
           "metrics": {"y": {"expr": "y"}}}
    errors = list(self.validator.iter_errors(cfg))
    self.assertEqual(errors, [], [e.message for e in errors])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd v3 && python3 -B -m unittest tests.test_schema_contract -v`
Expected: FAIL if the schema sets `additionalProperties: false` (resolve_by rejected). If it passes immediately, the schema is permissive — still add the property in Step 3 for documentation/intent, then re-run.

- [ ] **Step 3: Write minimal implementation**

```jsonc
// v3/schema/domain.schema.json — add to top-level "properties"
"resolve_by": {
  "type": "string",
  "description": "Optional ISO date when a binary forecast for this domain can be graded (e.g. \"2026-06-30\"). Pre-fills the Track-this-forecast form."
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd v3 && python3 -B -m unittest tests.test_schema_contract -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add v3/schema/domain.schema.json v3/tests/test_schema_contract.py
git commit -m "feat(schema): optional resolve_by date for binary domains"
```

---

### Task 6: Capture UI — "Track this forecast" button + modal

**Files:**
- Modify: `v3/static/index.html` — add `openTrackForecast` / `submitTrackForecast`; add a Track button to the binary branch of `renderStatCard` and to binary rows in `renderAsk`.
- Test: `v3/tests/test_calibration_ui.py` (CREATE)

**Interfaces:**
- Consumes: existing `POST /api/forecast` (accepts `question, predicted_prob, resolve_by, metric`); `currentConfig` (has `.context.decision` and, when authored, `.resolve_by`); per-metric stat `s.binary_prob`; existing `esc`, `showToast`, modal CSS classes.
- Produces: global `openTrackForecast(metric, prob)` and `submitTrackForecast(metric)`; a Track button rendered on binary-indicator stat cards and Ask rows.

- [ ] **Step 1: Write the failing test**

```python
# v3/tests/test_calibration_ui.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
HTML = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'index.html')).read()

class TestCaptureUI(unittest.TestCase):
    def test_track_button_present(self):
        self.assertIn("Track this forecast", HTML)
    def test_track_functions_present(self):
        self.assertIn("function openTrackForecast(", HTML)
        self.assertIn("function submitTrackForecast(", HTML)
    def test_track_posts_metric(self):
        # the submit handler logs the metric alongside the probability
        self.assertIn("predicted_prob", HTML)
        self.assertIn("metric: metric", HTML)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration_ui -v`
Expected: FAIL — strings not found.

- [ ] **Step 3: Write minimal implementation**

Add these two functions near the Predictions JS in `v3/static/index.html` (use the file's existing modal/form classes — mirror the Predictions/Ask modals):

```javascript
// Capture: track a binary-indicator forecast into the calibration ledger
function openTrackForecast(metric, prob) {
  const decision = (currentConfig && currentConfig.context && currentConfig.context.decision) || '';
  const q = decision || metric.replace(/_/g, ' ');
  const by = (currentConfig && currentConfig.resolve_by) || '';
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'track-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `
    <div class="modal" style="max-width:480px">
      <h2>Track this forecast</h2>
      <div class="form-hint">Logs a probability now so it can be graded against reality later — that track record is what makes the engine a forecasting instrument.</div>
      <label class="form-label" style="margin-top:10px">Question</label>
      <input id="track-q" class="form-input" value="${esc(q)}">
      <label class="form-label" style="margin-top:8px">Probability (%)</label>
      <input id="track-p" class="form-input" type="number" min="0" max="100" value="${(prob*100).toFixed(0)}">
      <label class="form-label" style="margin-top:8px">Resolve by (optional)</label>
      <input id="track-by" class="form-input" type="date" value="${esc(by)}">
      <div class="modal-actions" style="margin-top:14px">
        <button class="btn btn-run" onclick="submitTrackForecast('${esc(metric)}')">Track</button>
        <button class="btn btn-compare" onclick="document.getElementById('track-overlay').remove()">Cancel</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
}

async function submitTrackForecast(metric) {
  const q = document.getElementById('track-q').value.trim();
  const p = parseFloat(document.getElementById('track-p').value) / 100;
  const by = document.getElementById('track-by').value || null;
  if (!q) { showToast('Enter a question', 'error'); return; }
  if (!(p >= 0 && p <= 1)) { showToast('Probability must be 0–100', 'error'); return; }
  try {
    await fetch('/api/forecast', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, predicted_prob: p, resolve_by: by, metric: metric }),
    });
    document.getElementById('track-overlay').remove();
    showToast('Forecast tracked — grade it in Predictions when the outcome is known', 'success');
  } catch (e) {
    showToast('Could not track: ' + e, 'error');
  }
}
```

In `renderStatCard`, inside the existing `if (typeof s.binary_prob === 'number')` branch, add a Track button to the returned card (before the closing `</div>`):

```javascript
      <button class="btn-add-var" style="margin-top:6px;font-size:10px"
        onclick="event.stopPropagation();openTrackForecast('${name}', ${s.binary_prob})">Track this forecast</button>
```

In `renderAsk`, for binary rows (where `typeof s.binary_prob === 'number'`), append a small Track button cell or a button under the table that calls `openTrackForecast(k, s.binary_prob)`. (Ask has no `currentConfig.resolve_by`; the form's resolve-by stays blank for the user to pick.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration_ui -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add v3/static/index.html v3/tests/test_calibration_ui.py
git commit -m "feat(ui): one-click Track this forecast on binary results + Ask"
```

---

### Task 7: Viz UI — gated reliability diagram in the Predictions modal

**Files:**
- Modify: `v3/static/index.html` — add `drawReliability`; render the calibration section in `loadPredictions` from `data.calibration`.
- Test: `v3/tests/test_calibration_ui.py` (extend)

**Interfaces:**
- Consumes: `/api/forecasts` response `calibration` object (`{n, ready, min_n, curve, ece, base_rate}`); a `<canvas>`; existing `loadPredictions`.
- Produces: global `drawReliability(canvas, curve)`; a reliability canvas + ECE/base-rate line when `ready`, else a progress line.

- [ ] **Step 1: Write the failing test**

```python
# add to v3/tests/test_calibration_ui.py
class TestVizUI(unittest.TestCase):
    def test_draw_reliability_present(self):
        self.assertIn("function drawReliability(", HTML)
    def test_gate_copy_present(self):
        self.assertIn("calibration curve unlocks at", HTML)
    def test_reliability_canvas_present(self):
        self.assertIn("rel-canvas", HTML)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration_ui.TestVizUI -v`
Expected: FAIL — strings not found.

- [ ] **Step 3: Write minimal implementation**

Add the drawing helper in `v3/static/index.html`:

```javascript
// Reliability diagram: observed frequency vs predicted probability per bucket
function drawReliability(canvas, curve) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width = canvas.clientWidth || 360;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  const pad = 34;
  const X = p => pad + p * (W - 2 * pad);
  const Y = f => H - pad - f * (H - 2 * pad);
  // axes
  ctx.strokeStyle = '#2a3550'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pad, pad); ctx.lineTo(pad, H - pad); ctx.lineTo(W - pad, H - pad); ctx.stroke();
  // perfect-calibration diagonal
  ctx.strokeStyle = '#475569'; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(X(0), Y(0)); ctx.lineTo(X(1), Y(1)); ctx.stroke(); ctx.setLineDash([]);
  // points
  for (const b of curve) {
    const px = X(b.mean_predicted), py = Y(b.observed_freq);
    ctx.fillStyle = '#60a5fa';
    ctx.beginPath(); ctx.arc(px, py, 4, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = '#94a3b8'; ctx.font = '10px sans-serif';
    ctx.fillText('n=' + b.count, px + 6, py - 6);
  }
  ctx.fillStyle = '#64748b'; ctx.font = '10px sans-serif';
  ctx.fillText('predicted →', W - 70, H - 8);
  ctx.save(); ctx.translate(12, pad + 40); ctx.rotate(-Math.PI / 2);
  ctx.fillText('observed →', 0, 0); ctx.restore();
}
```

In `loadPredictions`, after the existing `scoreEl.innerHTML = ...` aggregate line, build and inject the calibration section from `data.calibration`:

```javascript
const cal = data.calibration || {};
let calHtml = '';
if (cal.ready && cal.curve && cal.curve.length) {
  calHtml = `<div style="margin-top:10px">
      <canvas id="rel-canvas" height="220" style="width:100%"></canvas>
      <div class="form-hint">Expected calibration error ${(cal.ece*100).toFixed(1)}% · base rate ${(cal.base_rate*100).toFixed(0)}% over ${cal.n} resolved (perfect = points on the dashed line)</div>
    </div>`;
} else if (cal.n != null && cal.n > 0) {
  calHtml = `<div class="form-hint" style="margin-top:10px">${cal.n}/${cal.min_n} resolved — the calibration curve unlocks at ${cal.min_n}.</div>`;
}
scoreEl.insertAdjacentHTML('afterend', calHtml);
if (cal.ready && cal.curve && cal.curve.length) {
  const c = document.getElementById('rel-canvas');
  if (c) drawReliability(c, cal.curve);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd v3 && python3 -B -m unittest tests.test_calibration_ui -v`
Expected: PASS (capture + viz)

- [ ] **Step 5: Full suite + commit**

```bash
make test    # expect OK
git add v3/static/index.html v3/tests/test_calibration_ui.py
git commit -m "feat(ui): gated reliability diagram in the Predictions modal"
```

---

## Final verification (after all tasks)

- [ ] `make test` is green.
- [ ] Manual smoke (optional, against a throwaway port to avoid the user's instance):
  `cd v3 && SIMENGINE_LEDGER_DB=/tmp/cal.db python3 server.py 8421`, run the BTC domain,
  click "Track this forecast", open Predictions, confirm the forecast appears and (after
  grading ≥10) the reliability diagram renders; below 10 the "N/10 resolved — unlocks at 10"
  line shows.

## Self-Review

**Spec coverage:**
- Capture (one-click, binary-only, inline modal, optional domain resolve_by) → Tasks 5, 6. ✓
- Reliability math (`reliability_curve`, `expected_calibration_error`, gated `calibration_report`, MIN_N=10) → Tasks 1, 2, 3. ✓
- `/api/forecasts` extension → Task 4. ✓
- Reliability diagram + gate UI → Task 7. ✓
- No DB migration (reuse `metric`/`resolve_by` columns) → confirmed; round-trip guard in Task 4. ✓
- Testing (TDD math, server shape, static-contract UI) → each task. ✓
- Out of scope (nudges, auto-resolve, CRPS, dedup, Wilson CIs) → not present in any task. ✓

**Placeholder scan:** No TBD/TODO; every code step shows real code. The one adaptive note (Ask Track-button placement, modal class names) instructs mirroring existing modals — acceptable, not a logic gap.

**Type consistency:** `reliability_curve` dict keys (`lo/hi/count/mean_predicted/observed_freq`) consistent across Tasks 1, 2, 7. `calibration_report` keys consistent across Tasks 3, 4, 7. `openTrackForecast(metric, prob)` / `submitTrackForecast(metric)` consistent across Task 6 hooks. ✓

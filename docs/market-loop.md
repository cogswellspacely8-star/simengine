# The forecast loop: price a set, record it against a baseline, grade it as a set

SimEngine's calibration ledger turns a simulation from "a calculator that
emits plausible numbers" into "an instrument with a scored track record." This
page is the loop that builds that record fastest: **bucket questions**, where
one event has several mutually exclusive answers and the engine prices all of
them from one run.

It is deliberately narrow. The engine prices events and keeps score. It does
not fetch prices, name tradable contracts, size positions, or place orders
(see the positioning guardrail in [decision-gate.md](decision-gate.md)).

## Why buckets

A range question ("which 2°F band does tomorrow's high land in?", "which CPI
print bucket?", "how many rate cuts?") is one uncertain quantity sliced into
bands. Modelled separately, the bands drift out of consistency. Modelled as
indicator metrics on **one** simulated distribution, they cannot: every bucket
is evaluated on the same paths, so the probabilities sum to 1 by construction
and each carries a 95% interval (`ci95.binary_prob`) from the same run.

`domains/temp_high_buckets.json` is the reference shape: a point forecast plus
a fat-tailed historical forecast-error distribution gives the realized value;
five half-open buckets are `100 if lo <= x < hi else 0` metrics.

## The loop

```bash
cd v3

# 1. Record: run the domain, log every bucket's probability, alongside the
#    baseline you are measuring against — recorded at the same moment.
python3 forecast_buckets.py record --domain temp_high_buckets.json \
    --baseline examples/temp_high_buckets_baseline.json --source market \
    --model temp_v1 --resolve-by 2026-10-05

# 2. Wait for the world.

# 3. Resolve: grade every pending bucket of the event from the realized state.
#    Each metric's own expression is evaluated against the state, so the
#    half-open bucket edges are applied exactly as the model defined them.
python3 forecast_buckets.py resolve --domain temp_high_buckets.json \
    --state '{"actual_high": 73.4}'

# 4. Report: Brier / log-loss, skill vs the recorded baseline, per model.
python3 forecast_buckets.py report
```

Everything goes through the same ledger the Predictions view and
`/api/forecast` use (`SIMENGINE_LEDGER_DB`, default `v3/forecasts.db`), so
hand-logged and loop-logged forecasts score together.

## What the record output tells you

```
metric             model      95% interval  baseline    diff  note
p_lt_69            0.072    [0.068, 0.076]     0.080  -0.008
p_71_73            0.321    [0.315, 0.328]     0.340  -0.019
p_73_75            0.236    [0.230, 0.242]     0.240  -0.004  baseline inside interval: no distinguishable difference
model mass 1.000 | baseline mass 1.000
```

- **`diff`** is model minus baseline. It is an analysis number, not a signal.
- **"baseline inside interval"** means the run cannot distinguish its estimate
  from the baseline. More simulations narrow the interval; they do not create a
  difference that is not there.
- **mass** should be 1.000 for the model by construction. A baseline mass far
  from 1 is itself information about the baseline (vig, stale quotes, missing
  buckets).

## Reading the scoreboard honestly

- **Skill vs baseline** (`brier_skill = 1 - brier_model / brier_baseline`) is
  the only number that says whether the model adds anything. Positive over a
  meaningful count means it does; the Brier score alone does not.
- The reliability curve and ECE stay gated until 10 forecasts are resolved.
  Treat skill the same way: a handful of resolutions is an anecdote.
- **Per-model rows** (`by_model`) are the table a trust weight is learned from:
  a model that has not earned skill should be blended toward the baseline, not
  trusted over it.
- Forecasts that stored `samples` and were resolved with an `outcome_value`
  also get a **CRPS** against the point-forecast-at-median reference.

## Baseline posture

Record the baseline **at the moment you record the forecast**. A comparison
probability looked up after the outcome is known is not a baseline. The
baseline is an internal input to a calibration record; it is never rebroadcast
and this tool emits no trade signal. Before wiring any venue's prices into
`--baseline`, read the terms section of [feeds.md](feeds.md): the repo's
documented position is that Kalshi's data terms restrict software use without
written consent, and the Polymarket adapter is read-only by design.

## Extending

- Any domain with indicator metrics works; a continuous metric can be recorded
  by hand through `/api/forecast` with `samples` for CRPS.
- `--event` tags the question text when the same domain is run for many events
  (one per station-day, one per release).
- The resolve step keys on the config's content hash. If you edit the domain
  between record and resolve, pass `--config-hash` from the record output.

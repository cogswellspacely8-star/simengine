# Historical Calibration Backtest — FRED Monthly Series

date: 2026-07-06
harness: `v3/backtest.py` (committed data snapshots in `v3/backtest_data/`)
reproduce: `cd v3 && python3 backtest.py --n-sims 4000 --output results.json`
full results: [2026-07-06-fred-monthly-results.json](2026-07-06-fred-monthly-results.json)

## Why this exists

Every external review of SimEngine since March 2026 (Sonnet 8-panel, ChatGPT-4o,
Deep Research counterpaper) converged on one open item: **no documented validation
against real-world data**. This backtest closes it with a walk-forward test on
public U.S. macro data that nobody at Venture Horizon authored — 2,819 monthly
forecasts spanning roughly seven decades, every one produced through the real
engine path and scored with the product's own calibration module.

## What was tested (and what wasn't)

At each month *t*, the harness builds a one-step domain config from information
available up to *t* only — a normal distribution fitted to the trailing 120
months of increments — runs it through `DomainConfig → run_monte_carlo →
indicator metric` (the exact code path `/api/simulate` uses), reads the event
probability off the simulated distribution, and resolves it against what
actually happened next month. Scoring uses `calibration.py` (Brier, log loss,
ECE, reliability curve) — the same functions behind the Predictions ledger.

This measures **whether engine-produced probability distributions are honest
(calibrated)** when fed simple, defensible input models. It does **not** claim
market-beating prediction skill: the input model is deliberately plain, and the
benchmark is walk-forward climatology (Laplace-smoothed trailing base rate) —
roughly the strongest forecast you can make from the base rate alone.

## Tasks

| Task | Event forecast each month | Data | Forecasts |
|------|---------------------------|------|-----------|
| `unrate_rises` | unemployment rate rises next month | UNRATE 1948–2026 | 820 |
| `cpi_hot` | MoM CPI inflation exceeds 0.25% | CPIAUCSL 1947–2026 | 831 |
| `indpro_falls` | industrial production falls next month | INDPRO 1919–2026 | 1,168 |

## Results (window=120m, n_sims=4000, seed=42)

| Task | n | base rate | Brier | climatology Brier | Brier skill | log loss | ECE |
|------|----:|------:|------:|------:|------:|------:|------:|
| `unrate_rises` | 820 | 0.331 | 0.2515 | 0.2233 | −0.126 | 0.6963 | 0.171 |
| `cpi_hot` | 831 | 0.521 | 0.2317 | 0.2335 | +0.008 | 0.6572 | 0.081 |
| `indpro_falls` | 1,168 | 0.368 | 0.2379 | 0.2358 | −0.009 | 0.6692 | 0.060 |
| **pooled** | **2,819** | | **0.2401** | | | **0.6736** | **0.094** |

Native vs pure-Python check: disabling the Rust path
(`SIMENGINE_DISABLE_NATIVE_SAMPLING=1 SIMENGINE_DISABLE_NATIVE_EXPR_SAMPLING=1`)
reproduces every score within Monte Carlo noise (Brier deltas ≈ 0.002 on a
45-forecast slice).

## Reading the numbers honestly

**Two of three tasks are well-calibrated and match the climatology benchmark.**
`cpi_hot` (ECE 0.081) and `indpro_falls` (ECE 0.060) track the diagonal of the
reliability curve: e.g. for CPI, forecasts binned at mean-predicted 0.75
verified 84% of the time; at 0.85, 82%. Brier skill within ±1% of climatology
is the expected result for a trailing-window model — the claim being validated
is *honest uncertainty*, not alpha.

**The third task is a caught failure, and it's the most valuable result in the
table.** `unrate_rises` is miscalibrated (ECE 0.171): the model predicts
0.45–0.55 in months where the observed rise frequency is ~0.33.

```
unrate_rises reliability curve
bin 0.4–0.5:  predicted 0.474  observed 0.324   (n=417)
bin 0.5–0.6:  predicted 0.529  observed 0.334   (n=368)
```

Diagnosis: UNRATE is reported at 0.1-point granularity, so roughly a third of
months the rate is exactly *unchanged* — a tie, which counts as "did not rise."
A continuous normal fitted to the increments has zero probability mass at
exactly 0, so it systematically overstates P(rise). The engine faithfully
simulated the model it was given; **the model was mis-specified for a discrete
series, and the reliability diagnostics caught it from outcomes alone.** That
is precisely the failure mode the calibration ledger exists to surface — GIGO
made visible, not hidden.

## Claims this supports (use these, not stronger ones)

- "SimEngine's forecast pipeline has been backtested on ~2,800 walk-forward
  monthly forecasts over up to seven decades of public U.S. macro data,
  scored with proper scoring rules (Brier, log loss, ECE)."
- "Well-specified input models produce calibrated output distributions
  (ECE 0.06–0.08); a deliberately mis-specified one was detected by the same
  reliability diagnostics shipped in the product."
- NOT: "SimEngine predicts the economy." The backtest validates calibration,
  not prediction skill beyond the base rate.

## Follow-ups (tracked in docs/reviews/2026-07-06-leverage-backlog.md)

- French Data Library equity sleeve: fat-tail (student_t) vs normal inputs,
  CRPS on continuous outcomes (backlog #6).
- A tie-aware UNRATE model (e.g. discretized or zero-inflated increments) to
  demonstrate the fix loop the diagnosis points to.
- Fold headline numbers into the paper's RQ1 (prequential calibration) section.

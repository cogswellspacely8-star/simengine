#!/usr/bin/env python3
"""
Historical calibration backtest for SimEngine.

Answers the longest-standing review question ("validated against what?") with
a walk-forward backtest on real public data: at each month t we build a small
domain config from information available up to t only, run it through the real
engine path (DomainConfig -> run_monte_carlo -> indicator metric), read the
event probability off the simulated distribution, and later score it against
what actually happened using the same proper scoring rules that power the
product's calibration ledger (calibration.py: Brier, log loss, ECE,
reliability curve).

What this does and does not claim:
  - It DOES measure whether engine-produced probability distributions are
    honest (calibrated) when fed simple, defensible input models.
  - It does NOT claim market-beating prediction skill. The input model is a
    deliberately plain one (trailing-window normal over monthly increments);
    the benchmark is walk-forward climatology (trailing base rate).

Offline by default: reads the committed CSV snapshots in backtest_data/.
`--fetch` refreshes them from FRED over stdlib urllib (keyless CSV endpoint);
network use is opt-in, same posture as feeds/. Zero third-party dependencies.

Usage:
    python3 backtest.py                       # run all tasks on snapshots
    python3 backtest.py --tasks unrate_rises  # one task
    python3 backtest.py --n-sims 4000 --window 120 --output results.json
    python3 backtest.py --fetch               # refresh snapshots from FRED
"""

import argparse
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kernel import DomainConfig, run_monte_carlo
from calibration import CalibrationLedger, brier_score, log_loss

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_data")
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

# Each task: one FRED monthly series, a stationary-ish increment transform,
# and a binary event on next month's increment.
TASKS = {
    "unrate_rises": {
        "csv": "UNRATE.csv",
        "transform": "diff",
        "op": ">",
        "threshold": 0.0,
        "question": "does the U.S. unemployment rate rise next month?",
    },
    "cpi_hot": {
        "csv": "CPIAUCSL.csv",
        "transform": "log_pct",
        "op": ">",
        "threshold": 0.25,
        "question": "does MoM CPI inflation exceed 0.25% next month?",
    },
    "indpro_falls": {
        "csv": "INDPRO.csv",
        "transform": "log_pct",
        "op": "<",
        "threshold": 0.0,
        "question": "does industrial production fall next month?",
    },
}

_OPS = {">", "<"}


# ---------------------------------------------------------------------------
# Data loading and transforms
# ---------------------------------------------------------------------------
def load_fred_csv(path):
    """Parse a FRED fredgraph.csv export into [(iso_date, float), ...].

    Rows whose value is missing ('.' or empty) are skipped.
    """
    series = []
    with open(path) as f:
        header = f.readline()
        if "," not in header:
            raise ValueError(f"{path}: not a FRED CSV (missing header)")
        for line in f:
            line = line.strip()
            if not line:
                continue
            date, _, raw = line.partition(",")
            raw = raw.strip()
            if raw in (".", ""):
                continue
            series.append((date, float(raw)))
    return series


def diffs(values):
    """First differences: values[i+1] - values[i]."""
    return [values[i + 1] - values[i] for i in range(len(values) - 1)]


def log_pct_changes(values):
    """Monthly log changes in percent: 100 * ln(v[i+1] / v[i])."""
    for v in values:
        if v <= 0:
            raise ValueError("log_pct_changes requires positive values")
    return [100.0 * math.log(values[i + 1] / values[i])
            for i in range(len(values) - 1)]


_TRANSFORMS = {"diff": diffs, "log_pct": log_pct_changes}


# ---------------------------------------------------------------------------
# The engine-path forecaster
# ---------------------------------------------------------------------------
def build_forecast_config(window, op, threshold, n_sims):
    """A one-step domain config: next month's increment z is modeled as
    normal(mean, std) fitted on the trailing window; the metric is a 0/1
    event indicator. The event probability is the metric's Monte Carlo mean.
    """
    if op not in _OPS:
        raise ValueError(f"op must be one of {sorted(_OPS)}, got {op!r}")
    mean = statistics.fmean(window)
    std = statistics.pstdev(window)
    if std <= 0.0:
        # Degenerate (constant) window: keep the distribution proper.
        std = max(abs(mean), 1.0) * 1e-6
    return {
        "name": "calibration-backtest step",
        "n_simulations": n_sims,
        "n_steps": 1,
        "parameters": {
            "z": {
                "distribution": "normal",
                "params": {"mean": mean, "std": std},
                "calibration": "trailing-window fit; see backtest.py",
            }
        },
        "step_logic": [
            {"target": "event", "expr": f"1 if z {op} {threshold} else 0"}
        ],
        "metrics": {"event": {"expr": "event", "format": "number"}},
    }


def forecast_prob(window, op, threshold, n_sims, seed):
    """Probability of the event, read off the real simulation path."""
    cfg = DomainConfig.from_dict(build_forecast_config(window, op, threshold, n_sims))
    result = run_monte_carlo(cfg, seed=seed)
    p = result["stats"]["event"]["mean"]
    return min(1.0, max(0.0, p))


def climatology_prob(events):
    """Walk-forward baseline: trailing base rate with Laplace smoothing
    (k+1)/(n+2) so the baseline never claims certainty."""
    k = sum(events)
    n = len(events)
    return (k + 1) / (n + 2)


# ---------------------------------------------------------------------------
# Rolling-origin backtest
# ---------------------------------------------------------------------------
def run_task(name, spec, data_dir=DEFAULT_DATA_DIR, window=120, n_sims=2000,
             seed=42, limit=None):
    """Walk the series forward. At each origin t (needing `window` months of
    history), forecast the event for month t+1 using ONLY z[t-window:t], then
    resolve against the realized z[t]. Returns the scored result dict.
    """
    series = load_fred_csv(os.path.join(data_dir, spec["csv"]))
    dates = [d for d, _ in series]
    values = [v for _, v in series]
    z = _TRANSFORMS[spec["transform"]](values)
    events = [1 if (z[i] > spec["threshold"] if spec["op"] == ">"
                    else z[i] < spec["threshold"]) else 0
              for i in range(len(z))]

    ledger = CalibrationLedger(":memory:")
    forecasts, clim_preds, outcomes = [], [], []
    origins = range(window, len(z))
    for t in origins:
        if limit is not None and len(forecasts) >= limit:
            break
        p = forecast_prob(z[t - window:t], spec["op"], spec["threshold"],
                          n_sims=n_sims, seed=seed + t)
        outcome = events[t]
        # dates[t+1] is the month whose increment z[t] describes
        month = dates[t + 1]
        fid = ledger.record(f"{spec['question']} ({month})", p,
                            metric="event", created_at=month)
        ledger.resolve(fid, outcome, resolved_at=month)
        clim_preds.append(climatology_prob(events[t - window:t]))
        outcomes.append(outcome)
        forecasts.append({"date": month, "p": round(p, 4), "outcome": outcome})

    score = ledger.score()
    report = ledger.calibration_report()
    clim_brier = brier_score(clim_preds, outcomes) if outcomes else None
    result = {
        "task": name,
        "question": spec["question"],
        "series": spec["csv"].rsplit(".", 1)[0],
        "n": score["n"],
        "first_forecast": forecasts[0]["date"] if forecasts else None,
        "last_forecast": forecasts[-1]["date"] if forecasts else None,
        "base_rate": round(sum(outcomes) / len(outcomes), 4) if outcomes else None,
        "brier": score["brier"],
        "log_loss": score["log_loss"],
        "ece": report.get("ece"),
        "reliability_curve": report.get("curve"),
        "climatology_brier": clim_brier,
        "climatology_log_loss": log_loss(clim_preds, outcomes) if outcomes else None,
        "brier_skill_vs_climatology": (
            1.0 - score["brier"] / clim_brier
            if score["brier"] is not None and clim_brier else None),
        "forecasts": forecasts,
    }
    return result


def run_backtest(task_names=None, data_dir=DEFAULT_DATA_DIR, window=120,
                 n_sims=2000, seed=42, limit=None):
    """Run every requested task plus a pooled all-tasks scoring pass."""
    names = task_names or list(TASKS)
    results, pooled_preds, pooled_outs = {}, [], []
    pooled = CalibrationLedger(":memory:")
    for name in names:
        res = run_task(name, TASKS[name], data_dir=data_dir, window=window,
                       n_sims=n_sims, seed=seed, limit=limit)
        results[name] = res
        for f in res["forecasts"]:
            fid = pooled.record(name, f["p"], created_at=f["date"])
            pooled.resolve(fid, f["outcome"], resolved_at=f["date"])
            pooled_preds.append(f["p"])
            pooled_outs.append(f["outcome"])
    pooled_score = pooled.score()
    pooled_report = pooled.calibration_report()
    return {
        "params": {"window_months": window, "n_sims": n_sims, "seed": seed,
                   "model": "trailing-window normal over monthly increments",
                   "baseline": "walk-forward climatology (Laplace-smoothed)"},
        "tasks": results,
        "overall": {
            "n": pooled_score["n"],
            "brier": pooled_score["brier"],
            "log_loss": pooled_score["log_loss"],
            "ece": pooled_report.get("ece"),
            "reliability_curve": pooled_report.get("curve"),
        },
    }


# ---------------------------------------------------------------------------
# Snapshot refresh (opt-in network)
# ---------------------------------------------------------------------------
def fetch_data(data_dir=DEFAULT_DATA_DIR, task_names=None):
    """Refresh the committed CSV snapshots from FRED (stdlib urllib only)."""
    import urllib.request
    os.makedirs(data_dir, exist_ok=True)
    names = task_names or list(TASKS)
    fetched = []
    for name in names:
        series_id = TASKS[name]["csv"].rsplit(".", 1)[0]
        url = FRED_CSV_URL.format(series=series_id)
        req = urllib.request.Request(url, headers={"User-Agent": "SimEngine-backtest"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        if not body.startswith("observation_date"):
            raise ValueError(f"unexpected FRED response for {series_id}")
        path = os.path.join(data_dir, TASKS[name]["csv"])
        with open(path, "w") as f:
            f.write(body)
        fetched.append(path)
    return fetched


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fmt(x, nd=4):
    return "-" if x is None else f"{x:.{nd}f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="SimEngine historical calibration backtest")
    ap.add_argument("--tasks", help="comma-separated task names (default: all)")
    ap.add_argument("--window", type=int, default=120, help="trailing window, months")
    ap.add_argument("--n-sims", type=int, default=2000, help="Monte Carlo runs per forecast")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, help="cap origins per task (for smoke runs)")
    ap.add_argument("--output", help="write full results JSON here")
    ap.add_argument("--fetch", action="store_true",
                    help="refresh CSV snapshots from FRED first (network)")
    args = ap.parse_args(argv)

    names = args.tasks.split(",") if args.tasks else None
    if names:
        unknown = [n for n in names if n not in TASKS]
        if unknown:
            ap.error(f"unknown tasks: {unknown}; available: {list(TASKS)}")

    if args.fetch:
        for p in fetch_data(task_names=names):
            print(f"fetched {p}")

    results = run_backtest(task_names=names, window=args.window,
                           n_sims=args.n_sims, seed=args.seed, limit=args.limit)

    print(f"\nSimEngine calibration backtest — window={args.window}m, "
          f"n_sims={args.n_sims}, seed={args.seed}")
    header = (f"{'task':<14} {'n':>5} {'base':>6} {'brier':>7} {'clim':>7} "
              f"{'skill':>7} {'logloss':>8} {'ece':>6}")
    print(header)
    print("-" * len(header))
    for name, r in results["tasks"].items():
        print(f"{name:<14} {r['n']:>5} {_fmt(r['base_rate'], 3):>6} "
              f"{_fmt(r['brier']):>7} {_fmt(r['climatology_brier']):>7} "
              f"{_fmt(r['brier_skill_vs_climatology'], 3):>7} "
              f"{_fmt(r['log_loss']):>8} {_fmt(r['ece'], 3):>6}")
    o = results["overall"]
    print("-" * len(header))
    print(f"{'ALL':<14} {o['n']:>5} {'':>6} {_fmt(o['brier']):>7} {'':>7} {'':>7} "
          f"{_fmt(o['log_loss']):>8} {_fmt(o['ece'], 3):>6}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nfull results -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
forecast_buckets — record, resolve and score a SET of bucket forecasts.

A bucket (range) question — "which 2°F band does tomorrow's high land in?",
"which CPI print bucket?" — is one event with several mutually exclusive
answers. SimEngine prices every bucket from the same simulated paths (each
bucket is an indicator metric on one run), so the set is internally
consistent. This tool closes the loop around that:

    record   run the domain, log every indicator metric's probability (with
             its 95% interval) to the calibration ledger — alongside the
             baseline you are measuring against, recorded at the same moment
    resolve  when the real value is known, grade every pending bucket of the
             event at once by evaluating each metric's own expression against
             the realized state (no hand-mapping of buckets to outcomes)
    report   Brier / log-loss, skill vs the recorded baseline, per-model table,
             CRPS for forecasts that stored samples

Examples:
    python3 forecast_buckets.py record  --domain temp_high_buckets.json \\
        --baseline examples/temp_high_buckets_baseline.json --source market \\
        --model temp_v1 --resolve-by 2026-10-05
    python3 forecast_buckets.py resolve --domain temp_high_buckets.json \\
        --state '{"actual_high": 73.4}'
    python3 forecast_buckets.py report

Posture: a baseline is an INTERNAL comparison input to a calibration record.
This tool never fetches a price, names a tradable contract, or places an order
(docs/decision-gate.md). Pure stdlib.
"""

import argparse
import ast
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kernel import (DomainConfig, run_monte_carlo, make_manifest, eval_expr,
                    indicator_probability, SAFE_BUILTINS)
from calibration import CalibrationLedger

DOMAIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "domains")
DEFAULT_DB = os.environ.get("SIMENGINE_LEDGER_DB",
                            os.path.join(os.path.dirname(os.path.abspath(__file__)), "forecasts.db"))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def load_domain(path_or_name):
    """A path, or a filename under domains/."""
    candidates = [path_or_name, os.path.join(DOMAIN_DIR, path_or_name)]
    for p in candidates:
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"domain not found: {path_or_name}")


def config_hash(data):
    """Content hash of the config (seed- and n-independent), the key that ties
    a recorded forecast back to the exact model that produced it."""
    return make_manifest(data, 0, None)["config_hash"]


def indicator_metrics(stats):
    """{metric: (p, ci95 or None)} for every indicator metric in a run."""
    out = {}
    for m, s in stats.items():
        p = indicator_probability(s)
        if p is None:
            # degenerate indicators (all 0 or all 100) have no binary_prob;
            # still record them if the raw value set says they are indicators
            continue
        ci = (s.get("ci95") or {}).get("binary_prob")
        out[m] = (p, ci)
    return out


def expression_names(expr):
    tree = ast.parse(expr, mode="eval")
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def outcome_from_state(metric_expr, state):
    """Evaluate the metric's own expression on the realized state. Refuses to
    guess: every name the expression uses must be supplied (the kernel would
    otherwise evaluate an unknown name to 0 and silently grade the bucket as
    a miss)."""
    allowed = set(SAFE_BUILTINS) | {"True", "False", "None"}
    missing = sorted(n for n in expression_names(metric_expr) if n not in state and n not in allowed)
    if missing:
        raise ValueError(f"state is missing names used by the metric: {missing}")
    value = eval_expr(metric_expr, dict(state))
    return 1 if value else 0


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_record(domain, *, baseline=None, source=None, model=None, resolve_by=None,
               seed=None, n_sims=None, db=DEFAULT_DB, event=None):
    data = load_domain(domain)
    cfg = DomainConfig.from_dict(data)
    seed = cfg.seed if seed is None else seed
    mc = run_monte_carlo(cfg, seed=seed, n_override=n_sims)
    chash = config_hash(data)
    buckets = indicator_metrics(mc["stats"])
    if not buckets:
        raise ValueError("domain has no indicator metrics (100 if cond else 0) to record")

    baseline_map = {}
    if baseline:
        with open(baseline, encoding="utf-8") as f:
            raw = json.load(f)
        baseline_map = {k: float(v) for k, v in raw.items() if not k.startswith("_")}

    led = CalibrationLedger(db)
    model = model or data.get("name", "unnamed")
    tag = event or data.get("name", "event")
    rows = []
    for m, (p, ci) in buckets.items():
        b = baseline_map.get(m)
        fid = led.record(f"{tag} :: {m}", p, config_hash=chash, metric=m,
                         resolve_by=resolve_by, baseline_prob=b,
                         baseline_source=source if b is not None else None, model=model)
        rows.append({"id": fid, "metric": m, "p_model": p, "ci95": ci, "p_baseline": b,
                     "diff": (round(p - b, 4) if b is not None else None),
                     "baseline_inside_ci95": (bool(ci and ci[0] <= b <= ci[1]) if (b is not None and ci) else None)})
    return {
        "domain": data.get("name"), "config_hash": chash, "model": model,
        "n_simulations": mc["n_simulations"], "seed": seed, "resolve_by": resolve_by,
        "model_mass": round(sum(r["p_model"] for r in rows), 4),
        "baseline_mass": (round(sum(baseline_map.get(r["metric"], 0) for r in rows), 4)
                          if baseline_map else None),
        "forecasts": rows,
    }


def cmd_resolve(domain, state, *, db=DEFAULT_DB, value_key=None, override_hash=None):
    data = load_domain(domain)
    cfg = DomainConfig.from_dict(data)
    chash = override_hash or config_hash(data)
    led = CalibrationLedger(db)
    pending = led.pending(config_hash=chash)
    if not pending:
        return {"config_hash": chash, "resolved": [],
                "note": "no pending forecasts for this config hash — if the domain file "
                        "changed since recording, pass --config-hash from the record output"}
    if value_key is None and len(state) == 1:
        value_key = next(iter(state))
    outcome_value = state.get(value_key) if value_key else None
    resolved = []
    for row in pending:
        m = row["metric"]
        if m not in cfg.metrics:
            resolved.append({"id": row["id"], "metric": m, "skipped": "metric not in domain"})
            continue
        outcome = outcome_from_state(cfg.metrics[m]["expr"], state)
        led.resolve(row["id"], outcome, outcome_value=outcome_value)
        resolved.append({"id": row["id"], "metric": m, "p_model": row["predicted_prob"],
                         "p_baseline": row["baseline_prob"], "outcome": outcome})
    hits = [r for r in resolved if r.get("outcome") == 1]
    return {"config_hash": chash, "outcome_value": outcome_value, "resolved": resolved,
            "buckets_hit": [r["metric"] for r in hits], "score": led.score()}


def cmd_report(*, db=DEFAULT_DB):
    led = CalibrationLedger(db)
    return {"pending": len(led.pending()), **led.calibration_report()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_record(res):
    print(f"{res['domain']}  (model={res['model']}, hash={res['config_hash']}, "
          f"n={res['n_simulations']:,}, seed={res['seed']})")
    print(f"{'metric':<16}{'model':>8}{'95% interval':>18}{'baseline':>10}{'diff':>8}  note")
    for r in res["forecasts"]:
        ci = f"[{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]" if r["ci95"] else "-"
        b = f"{r['p_baseline']:.3f}" if r["p_baseline"] is not None else "-"
        d = f"{r['diff']:+.3f}" if r["diff"] is not None else "-"
        note = ""
        if r["baseline_inside_ci95"] is True:
            note = "baseline inside interval: no distinguishable difference"
        print(f"{r['metric']:<16}{r['p_model']:>8.3f}{ci:>18}{b:>10}{d:>8}  {note}  (id {r['id']})")
    line = f"model mass {res['model_mass']:.3f}"
    if res["baseline_mass"] is not None:
        line += f" | baseline mass {res['baseline_mass']:.3f}"
    print(line)
    if res.get("resolve_by"):
        print(f"resolve by {res['resolve_by']}")


def _print_resolve(res):
    if not res["resolved"]:
        print(res.get("note", "nothing to resolve"))
        return
    print(f"resolved {len(res['resolved'])} bucket(s) for hash {res['config_hash']}"
          + (f" at value {res['outcome_value']}" if res["outcome_value"] is not None else ""))
    for r in res["resolved"]:
        if "skipped" in r:
            print(f"  {r['metric']:<16} skipped: {r['skipped']}")
            continue
        print(f"  {r['metric']:<16} model {r['p_model']:.3f}"
              + (f"  baseline {r['p_baseline']:.3f}" if r["p_baseline"] is not None else "")
              + f"  -> {'HIT' if r['outcome'] else 'miss'}")
    s = res["score"]
    print(f"ledger: n={s['n']} brier={s['brier']:.4f} log_loss={s['log_loss']:.4f}")
    if s.get("baseline"):
        b = s["baseline"]
        print(f"vs baseline ({', '.join(b['sources']) or 'unspecified'}): n={b['n']} "
              f"baseline brier={b['brier']:.4f} model brier={b['model_brier_on_same']:.4f} "
              f"skill={b['brier_skill']}")


def _print_report(rep):
    print(f"resolved {rep['n']} | pending {rep['pending']}")
    if rep["n"]:
        print(f"brier {rep['brier']}  log_loss {rep['log_loss']}  base_rate {rep['base_rate']}"
              + (f"  ece {rep['ece']}" if rep.get("ece") is not None else "  (curve gated until %d resolved)" % rep["min_n"]))
    if rep.get("baseline"):
        b = rep["baseline"]
        print(f"vs baseline: n={b['n']} baseline brier={b['brier']} model brier={b['model_brier_on_same']} skill={b['brier_skill']}")
    for g in rep.get("by_model", []):
        skill = g["baseline"]["brier_skill"] if g.get("baseline") else "-"
        print(f"  model {g['model']:<24} n={g['n']:<4} brier={g['brier']:<8} skill vs baseline={skill}")
    c = rep.get("continuous") or {}
    if c.get("n"):
        print(f"continuous: n={c['n']} crps={c['crps']} point_mae={c['point_mae']} skill={c['crps_skill_vs_point']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Record, resolve and score sets of bucket forecasts.")
    p.add_argument("--db", default=DEFAULT_DB, help="ledger sqlite path (default: SIMENGINE_LEDGER_DB or v3/forecasts.db)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="run a domain and log every indicator metric")
    r.add_argument("--domain", required=True)
    r.add_argument("--baseline", help="JSON file {metric: probability} recorded at the same moment")
    r.add_argument("--source", help="label for the baseline (e.g. market, climatology)")
    r.add_argument("--model", help="grouping key (default: domain name)")
    r.add_argument("--event", help="event tag prefixed to each question (default: domain name)")
    r.add_argument("--resolve-by", help="ISO date the outcome is known")
    r.add_argument("--seed", type=int)
    r.add_argument("--n-sims", type=int)

    s = sub.add_parser("resolve", help="grade every pending bucket of a domain from the realized state")
    s.add_argument("--domain", required=True)
    s.add_argument("--state", required=True, help='JSON of realized values, e.g. \'{"actual_high": 73.4}\'')
    s.add_argument("--value-key", help="which state key is the continuous outcome_value (default: the only key)")
    s.add_argument("--config-hash", help="override the hash to resolve (from record output)")

    sub.add_parser("report", help="calibration report: Brier, skill vs baseline, per model, CRPS")

    a = p.parse_args(argv)
    try:
        if a.cmd == "record":
            res = cmd_record(a.domain, baseline=a.baseline, source=a.source, model=a.model,
                             resolve_by=a.resolve_by, seed=a.seed, n_sims=a.n_sims, db=a.db, event=a.event)
            print(json.dumps(res, indent=2)) if a.json else _print_record(res)
        elif a.cmd == "resolve":
            state = json.loads(a.state)
            if not isinstance(state, dict):
                raise ValueError("--state must be a JSON object")
            res = cmd_resolve(a.domain, state, db=a.db, value_key=a.value_key, override_hash=a.config_hash)
            print(json.dumps(res, indent=2)) if a.json else _print_resolve(res)
        else:
            res = cmd_report(db=a.db)
            print(json.dumps(res, indent=2)) if a.json else _print_report(res)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

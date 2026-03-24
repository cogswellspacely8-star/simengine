#!/usr/bin/env python3
"""
SimEngine Quickstart
=====================
Demonstrates core SimEngine capabilities:
  1. Load a domain config
  2. Run a Monte Carlo simulation
  3. Interpret results (stats, safety, fitness)
  4. Bayesian-update parameters with observed data
  5. MCP server integration notes

Usage:
    cd simengine/v3
    python examples/quickstart.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kernel import DomainConfig, run_monte_carlo, evaluate_safety, compute_fitness
from bayesian import update_config


def main():
    print("=" * 60)
    print("SimEngine Quickstart")
    print("=" * 60)

    # ── 1. Load a domain config ──
    print("\n1. LOAD A DOMAIN CONFIG")
    print("-" * 40)
    domain_path = os.path.join(os.path.dirname(__file__), "..", "domains", "business_pipeline_v3.json")
    cfg = DomainConfig.from_json(domain_path)
    print(f"   Domain:     {cfg.name}")
    print(f"   Steps:      {cfg.n_steps} {cfg.step_label}s")
    print(f"   Parameters: {', '.join(cfg.parameters.keys())}")
    print(f"   Controls:   {', '.join(cfg.controls.keys())}")
    print(f"   Exogenous:  {', '.join(cfg.exogenous.keys())}")
    print(f"   Metrics:    {', '.join(cfg.metrics.keys())}")

    # ── 2. Run Monte Carlo simulation ──
    print("\n2. RUN MONTE CARLO SIMULATION (N=2,000)")
    print("-" * 40)
    mc = run_monte_carlo(cfg, seed=42, n_override=2000)
    for name, stats in mc["stats"].items():
        fmt = stats.get("format", "number")
        if fmt == "dollar":
            print(f"   {name:20s}  median ${stats['median']:>10,.0f}   "
                  f"(P10 ${stats['p10']:>10,.0f} -- P90 ${stats['p90']:>10,.0f})")
        elif fmt == "percent":
            print(f"   {name:20s}  median {stats['median']*100:>9.1f}%   "
                  f"(P10 {stats['p10']*100:>9.1f}% -- P90 {stats['p90']*100:>9.1f}%)")
        else:
            print(f"   {name:20s}  median {stats['median']:>10,.1f}   "
                  f"(P10 {stats['p10']:>10,.1f} -- P90 {stats['p90']:>10,.1f})")

    # ── 3. Evaluate safety constraints and fitness ──
    print("\n3. SAFETY CONSTRAINTS & FITNESS")
    print("-" * 40)
    safety = evaluate_safety(mc, cfg.safety)
    for c in safety.get("chance", []):
        status = "PASS" if c["passed"] else "FAIL"
        print(f"   [{status}] P({c['metric']} {c['condition']} "
              f"${c['threshold']:,}) = {c['actual_prob']:.1%}  (limit {c['max_prob']:.1%})")
    for c in safety.get("cvar", []):
        status = "PASS" if c["passed"] else "FAIL"
        print(f"   [{status}] CVaR({c['alpha']:.0%}) {c['metric']} "
              f"= ${c['actual_cvar']:,.0f}  (min ${c['min_cvar']:,})")

    fitness = compute_fitness(mc, cfg.fitness, cfg.safety)
    print(f"\n   Fitness score: {fitness:.1f} / 100")

    # ── 4. Bayesian updating with observed data ──
    print("\n4. BAYESIAN UPDATE WITH OBSERVED DATA")
    print("-" * 40)
    print("   Suppose after 3 months we observe:")
    print("     close_rate:      [0.25, 0.30, 0.28]")
    print("     leads_per_month: [4, 3, 5]")

    raw = json.load(open(domain_path))
    updated_config, report = update_config(raw, {
        "close_rate": [0.25, 0.30, 0.28],
        "leads_per_month": [4, 3, 5],
    })

    for var_name, r in report.items():
        if "prior_mean" in r:
            print(f"   {var_name}: prior={r['prior_mean']:.3f} -> "
                  f"posterior={r['posterior_mean']:.3f}  "
                  f"({r['method']}, {r['observations_used']} obs)")

    # Re-simulate with updated parameters
    updated_cfg = DomainConfig.from_dict(updated_config)
    mc2 = run_monte_carlo(updated_cfg, seed=42, n_override=2000)
    rev_before = mc["stats"]["annual_revenue"]["median"]
    rev_after = mc2["stats"]["annual_revenue"]["median"]
    delta = rev_after - rev_before
    print(f"\n   Revenue median: ${rev_before:,.0f} -> ${rev_after:,.0f} "
          f"({'+'if delta>=0 else ''}{delta:,.0f} after Bayesian update)")

    # ── 5. Integration options ──
    print("\n5. INTEGRATION OPTIONS")
    print("-" * 40)
    print("   Web UI:    python server.py  ->  http://localhost:8420")
    print("   CLI:       python kernel.py domains/business_pipeline_v3.json")
    print("   API:       POST /api/simulate with inline config JSON")
    print("   MCP:       Configure mcp_server.py in Claude Code settings")
    print("   Python:    from kernel import DomainConfig, run_monte_carlo")

    print("\n   MCP Server config for Claude Code:")
    print('   {')
    print('     "mcpServers": {')
    print('       "simengine": {')
    print('         "command": "python3",')
    print('         "args": ["<path-to-simengine>/v3/mcp_server.py"]')
    print('       }')
    print('     }')
    print('   }')

    print("\n" + "=" * 60)
    print("Done. See README.md for full documentation.")
    print("=" * 60)


if __name__ == "__main__":
    main()

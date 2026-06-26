#!/usr/bin/env python3
"""
SimEngine MCP Server — Model Context Protocol interface for SimEngine v3.
=========================================================================
Exposes SimEngine's Monte Carlo simulation capabilities as MCP tools
over the standard stdio JSON-RPC transport.

No external dependencies beyond the MCP SDK (pip install mcp).

# Claude Code settings.json snippet:
# {
#   "mcpServers": {
#     "simengine": {
#       "command": "python3",
#       "args": ["<path-to-simengine>/v3/mcp_server.py"]
#     }
#   }
# }
"""

import sys
import os
import json
import time
import copy

# Ensure SimEngine modules are importable
V3_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, V3_DIR)

from kernel import (
    DomainConfig, run_monte_carlo, evaluate_safety,
    compute_fitness, evolve, SAMPLERS
)
from bayesian import update_config
from diagnostics import (
    convergence_analysis, sensitivity_analysis,
    deterministic_baseline, compare_to_baseline
)

import glob as _glob

DOMAIN_DIR = os.path.join(V3_DIR, "domains")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_domains():
    results = []
    for f in sorted(_glob.glob(os.path.join(DOMAIN_DIR, "*.json"))):
        name = os.path.basename(f)
        if name.startswith("_"):
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            results.append({
                "file": name,
                "name": data.get("name", name),
                "description": data.get("description", ""),
                "n_steps": data.get("n_steps", 12),
                "step_label": data.get("step_label", "step"),
            })
        except Exception:
            pass
    return results


def _load_domain(filename):
    path = os.path.join(DOMAIN_DIR, os.path.basename(filename))
    with open(path) as f:
        return json.load(f)


def _validate_config(data):
    import math
    errors = []
    if not isinstance(data, dict):
        return ["Config must be a JSON object"]
    if not data.get("name"):
        errors.append("Missing 'name' field")
    n_steps = data.get("n_steps")
    if not isinstance(n_steps, int) or n_steps < 1:
        errors.append("'n_steps' must be a positive integer")
    has_vars = False
    for cat in ("parameters", "controls", "exogenous", "variables"):
        if data.get(cat) and isinstance(data[cat], dict):
            has_vars = True
            for vname, vdef in data[cat].items():
                dist = vdef.get("distribution")
                if dist not in SAMPLERS:
                    errors.append(f"Variable '{vname}': unknown distribution '{dist}'")
                if not vdef.get("params"):
                    errors.append(f"Variable '{vname}': missing 'params'")
    if not has_vars:
        errors.append("No variables defined")
    if not data.get("step_logic"):
        errors.append("Missing 'step_logic'")
    if not data.get("metrics"):
        errors.append("Missing 'metrics'")
    if not errors:
        try:
            cfg = DomainConfig.from_dict(data)
            mc = run_monte_carlo(cfg, seed=42, n_override=10)
            for mname in mc["stats"]:
                if math.isnan(mc["stats"][mname]["mean"]):
                    errors.append(f"Metric '{mname}' produced NaN")
        except Exception as e:
            errors.append(f"Test run failed: {str(e)}")
    return errors


def _generate_narrative(stats, safety):
    lines = []
    for mname, s in stats.items():
        fmt = s.get("format", "number")
        if fmt == "dollar":
            med, p10, p90 = f"${s['median']:,.0f}", f"${s['p10']:,.0f}", f"${s['p90']:,.0f}"
        elif fmt == "percent":
            med = f"{s['median']*100:.1f}%"
            p10 = f"{s['p10']*100:.1f}%"
            p90 = f"{s['p90']*100:.1f}%"
        else:
            med, p10, p90 = f"{s['median']:,.1f}", f"{s['p10']:,.1f}", f"{s['p90']:,.1f}"
        label = mname.replace("_", " ").title()
        lines.append(f"{label}: median {med} (80% range: {p10} to {p90})")
    if safety and not safety.get("all_passed", True):
        lines.append("")
        lines.append("RISK WARNINGS:")
        for c in safety.get("chance", []):
            if not c["passed"]:
                lines.append(f"  - P({c['metric']} {c['condition']} {c['threshold']:,}) = {c['actual_prob']:.1%} (limit {c['max_prob']:.1%})")
        for c in safety.get("cvar", []):
            if not c["passed"]:
                lines.append(f"  - CVaR({c['alpha']:.0%}) {c['metric']} = {c['actual_cvar']:,.0f} (min {c['min_cvar']:,})")
    elif safety:
        lines.append("\nAll safety constraints passed.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP Tool Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "simulate",
        "description": "Run a Monte Carlo simulation. Provide either a domain filename (from the domains/ directory) or an inline config JSON. Returns statistics, safety results, fitness score, and a narrative summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain config filename (e.g. 'saas_startup.json')"},
                "config": {"type": "object", "description": "Inline domain config JSON (alternative to domain filename)"},
                "overrides": {"type": "object", "description": "Dot-path overrides applied to the config, e.g. {'parameters.close_rate.params.mode': 0.35}"},
                "n_simulations": {"type": "integer", "description": "Number of simulations to run (default: from config)"},
                "seed": {"type": "integer", "description": "Random seed for reproducibility (default: 42)"},
            },
        },
    },
    {
        "name": "list_domains",
        "description": "List all available domain configuration files in the SimEngine domains/ directory.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "validate_config",
        "description": "Validate a domain configuration JSON. Returns whether it is valid and any errors found.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config": {"type": "object", "description": "The domain config JSON to validate"},
            },
            "required": ["config"],
        },
    },
    {
        "name": "optimize",
        "description": "Run evolutionary optimization on a domain to find the best control settings. Uses a genetic algorithm with safety constraints.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain config filename"},
                "generations": {"type": "integer", "description": "Number of GA generations (default: 15)"},
                "population": {"type": "integer", "description": "Population size per generation (default: 20)"},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "update_bayesian",
        "description": "Bayesian-update simulation parameters using real observed data. Uses conjugate prior updates (Beta-Binomial, Gamma-Poisson, Normal-Normal) to calibrate the model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain config filename"},
                "observations": {"type": "object", "description": "Map of variable_name to array of observed values, e.g. {'close_rate': [0.25, 0.30, 0.28]}"},
            },
            "required": ["domain", "observations"],
        },
    },
    {
        "name": "convergence_check",
        "description": "Run convergence diagnostics to verify that the simulation sample size is sufficient. Tests whether statistics stabilize as N increases.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain config filename"},
                "metric": {"type": "string", "description": "Target metric to check (default: first metric)"},
                "max_runs": {"type": "integer", "description": "Maximum runs to test (default: 10000)"},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "sensitivity_analysis",
        "description": "Run one-at-a-time sensitivity analysis to rank which input parameters drive the most output variance. Returns elasticity and relative importance scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain config filename"},
                "metric": {"type": "string", "description": "Target metric to analyze (default: first metric)"},
                "n_base": {"type": "integer", "description": "Base simulation count (default: 1000)"},
                "n_perturb": {"type": "integer", "description": "Perturbation trials per parameter (default: 10)"},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "baseline_comparison",
        "description": "Compare Monte Carlo simulation results to a deterministic (spreadsheet-style) single-point forecast. Shows the risk information hidden by deterministic forecasting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain config filename"},
                "n_simulations": {"type": "integer", "description": "MC simulation count (default: 5000)"},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "decide_under_uncertainty",
        "description": (
            "Decision gate for agents. Runs a Monte Carlo simulation and returns whether to "
            "PROCEED or ESCALATE based on how much of the OUTCOME distribution falls inside an "
            "acceptable range you specify. Returns the full outcome distribution plus a "
            "proceed/escalate flag and a plain-English reason. Use this to stop a multi-step "
            "agent from acting on an overconfident point estimate. NOTE: this models OUTCOME "
            "RISK (the spread of results given uncertain inputs) — not the language model's own "
            "token confidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain config filename (alternative to config)"},
                "config": {"type": "object", "description": "Inline domain config JSON (alternative to domain filename)"},
                "metric": {"type": "string", "description": "The output metric to evaluate the decision against"},
                "acceptable": {
                    "type": "object",
                    "description": "Acceptable range for the metric; provide at least one of 'min' or 'max'.",
                    "properties": {
                        "min": {"type": "number", "description": "Lowest acceptable value (omit for no lower bound)"},
                        "max": {"type": "number", "description": "Highest acceptable value (omit for no upper bound)"},
                    },
                },
                "min_confidence": {"type": "number", "description": "Probability mass that must fall within the acceptable range to proceed (default: 0.8)"},
                "n_simulations": {"type": "integer", "description": "Number of simulations to run (default: from config)"},
                "seed": {"type": "integer", "description": "Random seed for reproducibility (default: 42)"},
            },
            "required": ["metric", "acceptable"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

def handle_simulate(args):
    if args.get("config"):
        data = args["config"]
    elif args.get("domain"):
        data = _load_domain(args["domain"])
    else:
        return {"error": "Provide either 'domain' (filename) or 'config' (inline JSON)"}

    overrides = args.get("overrides", {})
    for key, value in overrides.items():
        parts = key.split(".")
        obj = data
        for p in parts[:-1]:
            obj = obj[p]
        obj[parts[-1]] = value

    seed = args.get("seed", 42)
    n_sims = args.get("n_simulations")

    cfg = DomainConfig.from_dict(data)
    t0 = time.time()
    mc = run_monte_carlo(cfg, seed=seed, n_override=n_sims)
    elapsed = round(time.time() - t0, 2)

    safety = {}
    if cfg.safety:
        safety = evaluate_safety(mc, cfg.safety)

    fitness = 0
    if cfg.fitness:
        fitness = compute_fitness(mc, cfg.fitness, cfg.safety)

    narrative = _generate_narrative(mc["stats"], safety)

    # Strip raw_metrics to keep response size reasonable
    return {
        "domain": mc["domain"],
        "n_simulations": mc["n_simulations"],
        "elapsed_seconds": elapsed,
        "stats": mc["stats"],
        "trajectories": mc["trajectories"],
        "safety": safety,
        "fitness": fitness,
        "narrative": narrative,
    }


def handle_list_domains(args):
    return {"domains": _list_domains()}


def handle_validate_config(args):
    config = args.get("config", {})
    errors = _validate_config(config)
    return {"valid": len(errors) == 0, "errors": errors}


def handle_optimize(args):
    domain = args["domain"]
    generations = args.get("generations", 15)
    population = args.get("population", 20)

    data = _load_domain(domain)
    t0 = time.time()
    result = evolve(data, generations=generations, population=population,
                    workers=1, verbose=False)
    elapsed = round(time.time() - t0, 1)

    return {
        "domain": result["domain"],
        "best_fitness": result["best"]["fitness"],
        "best_controls": result["best_controls"],
        "best_stats": result["best"]["stats"],
        "best_safety": result["best"]["safety"],
        "history": result["history"],
        "elapsed_seconds": elapsed,
    }


def handle_update_bayesian(args):
    domain = args["domain"]
    observations = args["observations"]

    data = _load_domain(domain)
    updated_config, report = update_config(data, observations)

    # Quick preview simulation with updated params
    cfg = DomainConfig.from_dict(updated_config)
    mc = run_monte_carlo(cfg, seed=42, n_override=1000)
    safety = evaluate_safety(mc, cfg.safety) if cfg.safety else {}

    return {
        "updated_config": updated_config,
        "update_report": report,
        "preview_stats": mc["stats"],
        "preview_safety": safety,
    }


def handle_convergence_check(args):
    domain = args["domain"]
    data = _load_domain(domain)
    cfg = DomainConfig.from_dict(data)
    metric = args.get("metric")
    max_runs = args.get("max_runs", 10000)

    t0 = time.time()
    result = convergence_analysis(cfg, metric=metric, max_runs=max_runs)
    result["elapsed_seconds"] = round(time.time() - t0, 2)
    return result


def handle_sensitivity_analysis(args):
    domain = args["domain"]
    data = _load_domain(domain)
    cfg = DomainConfig.from_dict(data)
    metric = args.get("metric")
    n_base = args.get("n_base", 1000)
    n_perturb = args.get("n_perturb", 10)

    t0 = time.time()
    result = sensitivity_analysis(cfg, metric=metric, n_base=n_base,
                                  n_perturb=n_perturb)
    result["elapsed_seconds"] = round(time.time() - t0, 2)
    return result


def handle_baseline_comparison(args):
    domain = args["domain"]
    data = _load_domain(domain)
    cfg = DomainConfig.from_dict(data)
    n_sims = args.get("n_simulations", 5000)

    t0 = time.time()
    result = compare_to_baseline(cfg, n_simulations=n_sims)
    result["elapsed_seconds"] = round(time.time() - t0, 2)
    return result


def handle_decide_under_uncertainty(args):
    if args.get("config"):
        data = args["config"]
    elif args.get("domain"):
        data = _load_domain(args["domain"])
    else:
        return {"error": "Provide either 'domain' (filename) or 'config' (inline JSON)"}

    metric = args.get("metric")
    if not metric:
        return {"error": "Provide 'metric': the output metric to evaluate the decision against"}

    acceptable = args.get("acceptable") or {}
    lo = acceptable.get("min")
    hi = acceptable.get("max")
    if lo is None and hi is None:
        return {"error": "Provide 'acceptable' with at least one of 'min' or 'max'"}

    min_confidence = args.get("min_confidence", 0.8)
    seed = args.get("seed", 42)
    n_sims = args.get("n_simulations")

    cfg = DomainConfig.from_dict(data)
    mc = run_monte_carlo(cfg, seed=seed, n_override=n_sims)
    raw = mc.get("raw_metrics", {})
    vals = raw.get(metric)
    if not vals:
        return {"error": f"Metric '{metric}' not found. Available metrics: {sorted(raw.keys())}"}

    def _within(v):
        if lo is not None and v < lo:
            return False
        if hi is not None and v > hi:
            return False
        return True

    n_within = sum(1 for v in vals if _within(v))
    prob = n_within / len(vals)
    proceed = prob >= min_confidence

    bounds = []
    if lo is not None:
        bounds.append(f">= {lo:,}")
    if hi is not None:
        bounds.append(f"<= {hi:,}")
    bound_str = " and ".join(bounds)

    if proceed:
        reason = (f"{prob:.0%} of {len(vals):,} simulated outcomes for '{metric}' fall "
                  f"within the acceptable range ({bound_str}) — at or above the "
                  f"{min_confidence:.0%} confidence required to proceed.")
    else:
        reason = (f"Only {prob:.0%} of {len(vals):,} simulated outcomes for '{metric}' fall "
                  f"within the acceptable range ({bound_str}); the {min_confidence:.0%} "
                  f"confidence required to proceed is not met. Escalate or gather more data.")

    return {
        "metric": metric,
        "decision": "proceed" if proceed else "escalate",
        "proceed": proceed,
        "probability_within_bounds": round(prob, 4),
        "min_confidence": min_confidence,
        "acceptable": {"min": lo, "max": hi},
        "distribution": mc["stats"].get(metric, {}),
        "n_simulations": mc["n_simulations"],
        "reason": reason,
    }


HANDLERS = {
    "simulate": handle_simulate,
    "list_domains": handle_list_domains,
    "validate_config": handle_validate_config,
    "optimize": handle_optimize,
    "update_bayesian": handle_update_bayesian,
    "convergence_check": handle_convergence_check,
    "sensitivity_analysis": handle_sensitivity_analysis,
    "baseline_comparison": handle_baseline_comparison,
    "decide_under_uncertainty": handle_decide_under_uncertainty,
}


# ---------------------------------------------------------------------------
# MCP Server — try SDK first, fall back to raw stdio JSON-RPC
# ---------------------------------------------------------------------------

def run_with_mcp_sdk():
    """Run using the official MCP Python SDK."""
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    import asyncio

    server = Server("simengine")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        handler = HANDLERS.get(name)
        if not handler:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            result = handler(arguments)
            return [TextContent(type="text", text=json.dumps(result, default=str))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(main())


def run_with_stdio_jsonrpc():
    """Fallback: raw JSON-RPC over stdin/stdout (MCP stdio transport)."""
    import io

    # Use binary mode for stdin/stdout to avoid encoding issues
    stdin = sys.stdin
    stdout = sys.stdout
    # Redirect any print output from SimEngine modules to stderr
    sys.stdout = sys.stderr

    def send(msg):
        text = json.dumps(msg) + "\n"
        stdout.write(text)
        stdout.flush()

    def handle_request(req):
        method = req.get("method", "")
        rid = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": rid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "simengine", "version": "3.0.0"},
                },
            }

        if method == "notifications/initialized":
            return None  # No response for notifications

        if method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": rid,
                "result": {"tools": TOOLS},
            }

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            handler = HANDLERS.get(tool_name)
            if not handler:
                return {
                    "jsonrpc": "2.0", "id": rid,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}],
                        "isError": True,
                    },
                }
            try:
                result = handler(arguments)
                return {
                    "jsonrpc": "2.0", "id": rid,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0", "id": rid,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                        "isError": True,
                    },
                }

        # Unknown method
        return {
            "jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            send(resp)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_with_mcp_sdk()
    except ImportError:
        # MCP SDK not installed — fall back to raw JSON-RPC
        print("MCP SDK not found, using raw stdio JSON-RPC transport", file=sys.stderr)
        run_with_stdio_jsonrpc()

#!/usr/bin/env python3
"""
Canonical SimEngine domain-config validation.
==============================================
Shared by the web server (/api/validate, /api/save-domain) and the LLM
compiler's repair loop. Returns a list of human-readable error strings;
an empty list means the config is valid. Pure stdlib.

(mcp_server.py still carries its own near-identical copy; fold it in here too
when it is next touched.)
"""

import math

from kernel import SAMPLERS, DomainConfig, run_monte_carlo


def validate_config(data):
    """Validate a domain config, return list of errors (empty = valid)."""
    errors = []
    if not isinstance(data, dict):
        return ["Config must be a JSON object"]

    if not data.get("name"):
        errors.append("Missing 'name' field")

    n_steps = data.get("n_steps")
    if not isinstance(n_steps, int) or n_steps < 1:
        errors.append("'n_steps' must be a positive integer")

    # Check variables exist
    has_vars = False
    for cat in ("parameters", "controls", "exogenous", "variables"):
        if data.get(cat) and isinstance(data[cat], dict):
            has_vars = True
            for vname, vdef in data[cat].items():
                dist = vdef.get("distribution")
                if dist not in SAMPLERS:
                    errors.append(f"Variable '{vname}': unknown distribution '{dist}'. Available: {', '.join(SAMPLERS.keys())}")
                if not vdef.get("params"):
                    errors.append(f"Variable '{vname}': missing 'params'")
    if not has_vars:
        errors.append("No variables defined (need at least one of: parameters, controls, exogenous)")

    if not data.get("step_logic"):
        errors.append("Missing 'step_logic' (at least one computation step needed)")
    else:
        for i, step in enumerate(data["step_logic"]):
            if not step.get("target"):
                errors.append(f"step_logic[{i}]: missing 'target'")
            if not step.get("expr") and not step.get("sample"):
                errors.append(f"step_logic[{i}]: missing 'expr' or 'sample'")

    if not data.get("metrics"):
        errors.append("Missing 'metrics' (need at least one output metric)")

    # Try a quick test run
    if not errors:
        try:
            cfg = DomainConfig.from_dict(data)
            mc = run_monte_carlo(cfg, seed=42, n_override=10)
            for mname in mc["stats"]:
                if math.isnan(mc["stats"][mname]["mean"]):
                    errors.append(f"Metric '{mname}' produced NaN — check your expressions")
        except Exception as e:
            errors.append(f"Test run failed: {str(e)}")

    return errors

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

import ast
import math

from kernel import SAMPLERS, DomainConfig, run_monte_carlo, SAFE_BUILTINS

_ALLOWED_FUNCS = set(SAFE_BUILTINS.keys())
_PY_CONSTANTS = {"True", "False", "None"}


def _known_names(data):
    """Every name an expression may legally reference."""
    names = set(_ALLOWED_FUNCS) | _PY_CONSTANTS | {"_step"}
    for cat in ("parameters", "controls", "exogenous", "variables"):
        if isinstance(data.get(cat), dict):
            names.update(data[cat].keys())
    if isinstance(data.get("accumulators"), dict):
        names.update(data["accumulators"].keys())
    if isinstance(data.get("initial_state"), dict):
        names.update(data["initial_state"].keys())
    for step in data.get("step_logic", []) or []:
        if isinstance(step, dict) and step.get("target"):
            names.add(step["target"])
    return names


def available_names(data):
    """The names a config defines that an expression may reference (vars,
    accumulators, step targets, initial_state) — used to coach the repair loop."""
    names = set()
    for cat in ("parameters", "controls", "exogenous", "variables"):
        if isinstance(data.get(cat), dict):
            names.update(data[cat].keys())
    if isinstance(data.get("accumulators"), dict):
        names.update(data["accumulators"].keys())
    if isinstance(data.get("initial_state"), dict):
        names.update(data["initial_state"].keys())
    for step in data.get("step_logic", []) or []:
        if isinstance(step, dict) and step.get("target"):
            names.add(step["target"])
    return sorted(names)


def _iter_exprs(data):
    """Yield (label, expr_string) for every expression the kernel evaluates."""
    for i, step in enumerate(data.get("step_logic", []) or []):
        if isinstance(step, dict) and isinstance(step.get("expr"), str):
            yield (f"step_logic[{i}] '{step.get('target', '?')}'", step["expr"])
    if isinstance(data.get("accumulators"), dict):
        for k, v in data["accumulators"].items():
            if isinstance(v, str):
                yield (f"accumulator '{k}'", v)
    if isinstance(data.get("metrics"), dict):
        for k, m in data["metrics"].items():
            if isinstance(m, dict) and isinstance(m.get("expr"), str):
                yield (f"metric '{k}'", m["expr"])


def check_expression_names(data):
    """Statically flag names/constructs the kernel can't evaluate.

    The kernel's eval_expr returns 0 on ANY error (undefined name, bad call),
    so an expression like `clamp(x, 0, inf)` silently zeroes the result instead
    of failing. This catches that class before it produces nonsense, and the
    messages feed the LLM compiler's repair loop.
    """
    errors = []
    known = _known_names(data)
    for label, expr in _iter_exprs(data):
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            errors.append(f"{label}: invalid expression syntax ({e.msg})")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Lambda):
                errors.append(f"{label}: lambda is not supported in expressions")
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                errors.append(f"{label}: comprehensions are not supported — per-step values are single numbers, not lists")
            elif isinstance(node, ast.Attribute):
                errors.append(f"{label}: dotted names like 'x.{node.attr}' are not allowed — reference a variable or accumulator by its plain name")
            elif isinstance(node, ast.Name) and node.id not in known:
                errors.append(f"{label}: unknown name '{node.id}' — not a defined variable, accumulator, step target, or allowed function")
    # de-duplicate, preserve order
    seen, out = set(), []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


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
                if not isinstance(vdef, dict):
                    errors.append(f"Variable '{vname}' must be an object like {{\"distribution\": ..., \"params\": {{...}}}}, got {type(vdef).__name__}. (Constants need {{\"distribution\": \"fixed\", \"params\": {{\"value\": N}}}}.)")
                    continue
                dist = vdef.get("distribution")
                if dist not in SAMPLERS:
                    errors.append(f"Variable '{vname}': unknown distribution '{dist}'. Available: {', '.join(SAMPLERS.keys())}")
                if not vdef.get("params"):
                    errors.append(f"Variable '{vname}': missing 'params'")
    if not has_vars:
        errors.append("No variables defined (need at least one of: parameters, controls, exogenous)")

    if not data.get("step_logic"):
        errors.append("Missing 'step_logic' (at least one computation step needed)")
    elif not isinstance(data["step_logic"], list):
        errors.append("'step_logic' must be a list of steps, each an object with 'target' and 'expr'")
    else:
        for i, step in enumerate(data["step_logic"]):
            if not isinstance(step, dict):
                errors.append(f"step_logic[{i}] must be an object with 'target' and 'expr', got {type(step).__name__}")
                continue
            if not step.get("target"):
                errors.append(f"step_logic[{i}]: missing 'target'")
            if not step.get("expr") and not step.get("sample"):
                errors.append(f"step_logic[{i}]: missing 'expr' or 'sample'")

    if not data.get("metrics"):
        errors.append("Missing 'metrics' (need at least one output metric)")

    # Static check: every name in an expression must resolve (the kernel would
    # otherwise silently evaluate undefined names to 0).
    if not errors:
        errors.extend(check_expression_names(data))

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

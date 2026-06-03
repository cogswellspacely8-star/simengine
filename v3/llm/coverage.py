#!/usr/bin/env python3
"""
Fidelity / coverage check: a separate, skeptical pass that compares the user's
question against what the generated config ACTUALLY computes, so a reduced or
unfaithful model is reported instead of silently answered.

This is the guard against the worst failure mode: a hyper-specified, over-complex
prompt gets compiled into a degenerate config that validates and runs, and the
explainer then fabricates a confident answer the simulation never produced.

Fails OPEN: on any error it returns fidelity "unknown" so it never blocks a
legitimate answer or raises a false alarm.
"""

from .backends import complete as _default_complete, LLMError
from .prompts import COVERAGE_SYSTEM, coverage_user_prompt
from .compiler import _extract_json


def assess_coverage(question, config, results, *, backend=None, model=None, _complete=None):
    """Return {"fidelity": full|partial|low|unknown, "captured": [...], "missing": [...], "note": str}."""
    config = config or {}
    metrics = {k: (v.get("expr") if isinstance(v, dict) else v)
               for k, v in (config.get("metrics") or {}).items()}
    variables = sorted(set(
        list((config.get("parameters") or {}).keys())
        + list((config.get("controls") or {}).keys())
        + list((config.get("exogenous") or {}).keys())
    ))
    targets = [s.get("target") for s in (config.get("step_logic") or [])
               if isinstance(s, dict) and s.get("target")]

    complete_fn = _complete or _default_complete
    messages = [
        {"role": "system", "content": COVERAGE_SYSTEM},
        {"role": "user", "content": coverage_user_prompt(question, metrics, variables, targets)},
    ]
    try:
        text = complete_fn(messages, json_mode=True, backend=backend, model=model)
        data = _extract_json(text)
    except (LLMError, ValueError):
        return {"fidelity": "unknown", "captured": [], "missing": [], "note": ""}

    fidelity = data.get("fidelity")
    if fidelity not in ("full", "partial", "low"):
        fidelity = "unknown"
    captured = data.get("captured") if isinstance(data.get("captured"), list) else []
    missing = data.get("missing") if isinstance(data.get("missing"), list) else []
    return {
        "fidelity": fidelity,
        "captured": [str(c) for c in captured][:8],
        "missing": [str(m) for m in missing][:8],
        "note": str(data.get("note", ""))[:300],
    }

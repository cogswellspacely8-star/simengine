#!/usr/bin/env python3
"""
NL -> SimEngine config compiler with a validate/repair loop.

The model does not have to be right in one shot — it has to be correctable.
We draft a config, validate it with the engine's own validator, and feed the
exact errors back until it passes (or we run out of repair rounds). This is
what makes small local models reliable here.
"""

import json

from .backends import complete as _default_complete
from .prompts import SYSTEM_PROMPT, user_prompt, repair_message
from validation import validate_config


def _extract_json(text):
    """Pull a JSON object out of a model reply, tolerating fences and prose."""
    if not text or not text.strip():
        raise ValueError("empty output")
    s = text.strip()
    # Try the whole thing first.
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Strip a ```json ... ``` (or ``` ... ```) fence if present.
    if "```" in s:
        inner = s.split("```", 2)
        if len(inner) >= 2:
            block = inner[1]
            if block.lstrip().lower().startswith("json"):
                block = block.split("\n", 1)[1] if "\n" in block else ""
            try:
                obj = json.loads(block.strip())
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
    # Fall back to the first balanced {...} span.
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(s[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise ValueError("no JSON object found in model output")


def compile_config(question, *, n_simulations=None, max_repairs=3,
                   backend=None, model=None, _complete=None):
    """Turn a question into a validated SimEngine config.

    Returns {"config": dict|None, "valid": bool, "attempts": int, "errors": [str]}.
    Never raises on a bad model reply — it reports the failure.
    """
    complete_fn = _complete or _default_complete
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(question, n_simulations)},
    ]

    config = None
    last_errors = ["no attempts made"]
    attempts = 0

    for _ in range(max_repairs + 1):
        text = complete_fn(messages, json_mode=True, backend=backend, model=model)
        attempts += 1
        try:
            config = _extract_json(text)
        except ValueError as e:
            errors = [f"Output was not valid JSON: {e}"]
        else:
            if n_simulations and isinstance(config, dict):
                config.setdefault("n_simulations", n_simulations)
            errors = validate_config(config)

        if not errors:
            return {"config": config, "valid": True, "attempts": attempts, "errors": []}

        last_errors = errors
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": repair_message(errors)})

    return {"config": config, "valid": False, "attempts": attempts, "errors": last_errors}

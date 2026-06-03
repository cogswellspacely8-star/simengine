#!/usr/bin/env python3
"""
Explain a simulation result in plain language, grounded only in the real numbers.

If the LLM backend is unavailable or returns nothing, fall back to the engine's
deterministic narrative — so the user always gets an answer.
"""

from .backends import complete as _default_complete, LLMError
from .prompts import EXPLAIN_SYSTEM, explain_user_prompt


def explain_results(question, results, config=None, coverage=None, *, backend=None, model=None, _complete=None):
    """Return a plain-language answer to `question`, grounded in `results`.

    `config` lets the explainer state assumptions; `coverage` (the fidelity
    verdict) forces it to disclaim what the model did not compute.
    Falls back to results["narrative"] when the LLM cannot be reached.
    """
    complete_fn = _complete or _default_complete
    messages = [
        {"role": "system", "content": EXPLAIN_SYSTEM},
        {"role": "user", "content": explain_user_prompt(question, results, config, coverage)},
    ]
    try:
        text = complete_fn(messages, backend=backend, model=model)
        if text and text.strip():
            return text.strip()
    except LLMError:
        pass
    return results.get("narrative") or "(no explanation available)"

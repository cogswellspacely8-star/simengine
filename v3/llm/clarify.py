#!/usr/bin/env python3
"""
Pre-check a question for enough detail to model. If it's too vague, return
clarifying questions instead of letting the model silently invent assumptions.

Fails OPEN: if the classifier errors or returns junk, we treat the question as
ready and proceed (better to model with stated assumptions than to block).
"""

from .backends import complete as _default_complete, LLMError
from .prompts import CLARIFY_SYSTEM, clarify_user_prompt
from .compiler import _extract_json


def assess_question(question, *, backend=None, model=None, _complete=None):
    """Return {"ready": bool, "questions": [str]} for a question."""
    complete_fn = _complete or _default_complete
    messages = [
        {"role": "system", "content": CLARIFY_SYSTEM},
        {"role": "user", "content": clarify_user_prompt(question)},
    ]
    try:
        text = complete_fn(messages, json_mode=True, backend=backend, model=model)
        data = _extract_json(text)
    except (LLMError, ValueError):
        return {"ready": True, "questions": []}  # fail open

    ready = bool(data.get("ready", True))
    questions = data.get("questions") or []
    if not isinstance(questions, list):
        questions = []
    questions = [str(q) for q in questions][:3]
    # If it claims "not ready" but offers no questions, don't block the user.
    if not ready and not questions:
        ready = True
    return {"ready": ready, "questions": questions}

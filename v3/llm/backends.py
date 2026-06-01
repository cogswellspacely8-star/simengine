#!/usr/bin/env python3
"""
Provider-agnostic LLM chat for SimEngine (OPT-IN, stdlib urllib only).

One entry point, `complete(messages, ...)`, dispatched to a backend chosen by
the SIMENGINE_LLM_BACKEND environment variable (default "ollama"). Backends:

  - ollama     local, default. POST {OLLAMA_HOST}/api/chat, uses Ollama JSON mode.
  - openai     OpenAI-compatible. POST {OPENAI_BASE_URL}/chat/completions.
               The configurable base URL also covers llama.cpp / LM Studio / vLLM.
  - anthropic  POST https://api.anthropic.com/v1/messages.

All network I/O goes through an injectable transport (`_post`) so tests never
touch the network. Errors are raised as LLMError with an actionable message.
"""

import os
import json

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_MODELS = {
    "ollama": "qwen2.5",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
}


class LLMError(Exception):
    """Raised when an LLM backend is unreachable, unconfigured, or misbehaves."""


# ---------------------------------------------------------------------------
# Transport (the only network surface; injectable for tests)
# ---------------------------------------------------------------------------

def _default_post(url, headers, payload, timeout=None):
    import urllib.request
    if timeout is None:
        timeout = float(os.environ.get("SIMENGINE_LLM_TIMEOUT", "120"))
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _resolve_backend(backend):
    return (backend or os.environ.get("SIMENGINE_LLM_BACKEND") or "ollama").lower()


def _resolve_model(backend, model):
    return model or os.environ.get("SIMENGINE_LLM_MODEL") or DEFAULT_MODELS.get(backend, "qwen2.5")


def _hint(backend):
    if backend == "ollama":
        host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        return (f"Is Ollama running at {host}? Install it from https://ollama.com, "
                "then `ollama pull qwen2.5`. Or set SIMENGINE_LLM_BACKEND=openai with an OPENAI_API_KEY.")
    if backend == "openai":
        return "Check OPENAI_API_KEY, OPENAI_BASE_URL, and your network."
    return "Check your API key and network."


# ---------------------------------------------------------------------------
# Per-backend request builders -> (url, headers, payload)  and response parsers
# ---------------------------------------------------------------------------

def _build_ollama(messages, model, temperature, json_mode):
    host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).rstrip("/")
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"
    return f"{host}/api/chat", {}, payload


def _parse_ollama(resp):
    return resp["message"]["content"]


def _build_openai(messages, model, temperature, json_mode):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise LLMError("OPENAI_API_KEY is not set. " + _hint("openai"))
    base = os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE).rstrip("/")
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return f"{base}/chat/completions", {"Authorization": f"Bearer {key}"}, payload


def _parse_openai(resp):
    return resp["choices"][0]["message"]["content"]


def _build_anthropic(messages, model, temperature, json_mode):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not set. " + _hint("anthropic"))
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    convo = [m for m in messages if m.get("role") != "system"]
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": temperature,
        "messages": convo,
    }
    if system:
        payload["system"] = system
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return "https://api.anthropic.com/v1/messages", headers, payload


def _parse_anthropic(resp):
    return resp["content"][0]["text"]


_BACKENDS = {
    "ollama": (_build_ollama, _parse_ollama),
    "openai": (_build_openai, _parse_openai),
    "anthropic": (_build_anthropic, _parse_anthropic),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def complete(messages, *, model=None, temperature=0.0, json_mode=False,
             backend=None, _post=None):
    """Send a chat completion and return the assistant's text.

    messages: list of {"role": "system"|"user"|"assistant", "content": str}
    json_mode: ask the backend to return strict JSON where supported.
    backend / model: override the env defaults.
    _post: injectable transport (url, headers, payload, timeout) -> dict.
    """
    b = _resolve_backend(backend)
    if b not in _BACKENDS:
        raise LLMError(f"Unknown backend '{b}'. Use one of: {', '.join(_BACKENDS)}")
    build, parse = _BACKENDS[b]
    model = _resolve_model(b, model)
    url, headers, payload = build(messages, model, temperature, json_mode)
    post = _post or _default_post
    try:
        resp = post(url, headers, payload)
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Could not reach the {b} backend at {url}: {e}. {_hint(b)}")
    try:
        return parse(resp)
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected response shape from the {b} backend: {e}")

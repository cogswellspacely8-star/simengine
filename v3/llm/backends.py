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
    "deepseek": "deepseek-chat",
}


class LLMError(Exception):
    """Raised when an LLM backend is unreachable, unconfigured, or misbehaves."""


class LLMHTTPError(LLMError):
    """An HTTP error from a backend, carrying the status code and response body."""

    def __init__(self, status, body=""):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


# ---------------------------------------------------------------------------
# Transport (the only network surface; injectable for tests)
# ---------------------------------------------------------------------------

def _default_post(url, headers, payload, timeout=None):
    import urllib.request
    import urllib.error
    if timeout is None:
        timeout = float(os.environ.get("SIMENGINE_LLM_TIMEOUT", "120"))
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        raise LLMHTTPError(e.code, body)


def _default_get(url, timeout=None):
    import urllib.request
    if timeout is None:
        timeout = float(os.environ.get("SIMENGINE_LLM_TIMEOUT", "120"))
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_ollama_models(_get=None):
    """Return the names of models installed in Ollama, or [] if it can't be reached."""
    get = _get or _default_get
    host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).rstrip("/")
    try:
        data = get(f"{host}/api/tags")
        return [m["name"] for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def suggest_ollama_model(preferred=None, _get=None):
    """Pick a usable installed model: `preferred` if present, else a sensible
    instruct/chat model from what's installed, else None."""
    installed = list_ollama_models(_get=_get)
    if not installed:
        return None
    if preferred and preferred in installed:
        return preferred
    prefer_substrings = ["qwen2.5", "instruct", "hermes", "llama3", "mistral", "qwen", "deepseek"]
    for sub in prefer_substrings:
        for name in installed:
            if sub in name.lower() and "embed" not in name.lower():
                return name
    for name in installed:
        if "embed" not in name.lower():
            return name
    return installed[0]


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
    if backend == "deepseek":
        return "Check DEEPSEEK_API_KEY and your network."
    return "Check your API key and network."


def _explain_http_error(backend, model, err):
    """Turn a raw HTTP error into an actionable message."""
    if backend == "ollama" and err.status == 404:
        return LLMError(
            f"Ollama has no model named '{model}'. Pull it with `ollama pull {model}`, "
            f"choose one you already have (run `ollama list`), or set SIMENGINE_LLM_MODEL "
            f"/ pass --model."
        )
    if err.status in (401, 403):
        return LLMError(f"The {backend} backend rejected the request (HTTP {err.status}). {_hint(backend)}")
    return LLMError(f"The {backend} backend returned HTTP {err.status}: {err.body} {_hint(backend)}")


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


def _build_deepseek(messages, model, temperature, json_mode):
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise LLMError("DEEPSEEK_API_KEY is not set. Get a key at https://platform.deepseek.com.")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return f"{base}/chat/completions", {"Authorization": f"Bearer {key}"}, payload


_BACKENDS = {
    "ollama": (_build_ollama, _parse_ollama),
    "openai": (_build_openai, _parse_openai),
    "anthropic": (_build_anthropic, _parse_anthropic),
    "deepseek": (_build_deepseek, _parse_openai),  # DeepSeek is OpenAI-compatible
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
    except LLMHTTPError as e:
        raise _explain_http_error(b, model, e)
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Could not reach the {b} backend at {url}: {e}. {_hint(b)}")
    try:
        return parse(resp)
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected response shape from the {b} backend: {e}")

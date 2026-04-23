"""
Optional native acceleration loader for SimEngine.

The pure-Python engine remains the default. This module only exposes the
compiled backend when it is available in the active Python environment.
"""

from __future__ import annotations

_NATIVE_BACKEND = None
_IMPORT_ERROR = None

try:
    import simengine_native as _NATIVE_BACKEND
except Exception as exc:  # pragma: no cover - depends on local build state
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


def get_native_backend():
    return _NATIVE_BACKEND


def native_available() -> bool:
    return _NATIVE_BACKEND is not None


def native_import_error():
    return _IMPORT_ERROR


def backend_info() -> dict:
    if _NATIVE_BACKEND is None:
        return {"available": False, "error": _IMPORT_ERROR}
    info = dict(_NATIVE_BACKEND.backend_info())
    info["available"] = True
    return info

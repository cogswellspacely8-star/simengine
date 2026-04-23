#!/usr/bin/env python3
"""
Small reducer benchmark for the optional native backend.

Run from the repo root:
    python3 scripts/bench_native.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "v3"))

import kernel  # noqa: E402
import native  # noqa: E402


def main() -> int:
    config_path = REPO_ROOT / "v3" / "domains" / "saas_startup.json"
    cfg = kernel.DomainConfig.from_json(str(config_path))

    start = time.perf_counter()
    mc = kernel.run_monte_carlo(cfg, seed=42, n_override=1000)
    elapsed = time.perf_counter() - start

    print(json.dumps(
        {
            "native_available": native.native_available(),
            "native_info": native.backend_info(),
            "native_batch_sampling_disabled": bool(os.environ.get("SIMENGINE_DISABLE_NATIVE_SAMPLING")),
            "native_expr_sampling_disabled": bool(os.environ.get("SIMENGINE_DISABLE_NATIVE_EXPR_SAMPLING")),
            "expr_compile_cache_disabled": bool(os.environ.get("SIMENGINE_DISABLE_EXPR_CACHE")),
            "elapsed_seconds": round(elapsed, 3),
            "metrics": list(mc["stats"].keys()),
            "sample_metric": next(iter(mc["stats"].items())),
        },
        indent=2,
        default=str,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

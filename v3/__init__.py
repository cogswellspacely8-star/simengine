"""SimEngine v3 — Universal Simulation Kernel + Diagnostics."""
import os
import sys

# Sibling modules (kernel.py, diagnostics.py, bayesian.py, server.py, ...) use
# flat absolute imports (e.g. `from kernel import ...`) because the in-repo
# entry points run as scripts with this directory on sys.path. When this
# package is installed (e.g. as `simengine_mcp`), those flat imports would
# otherwise fail — so mirror the same sys.path arrangement here, before
# importing anything that might trigger them.
sys.path.insert(0, os.path.dirname(__file__))

from .kernel import DomainConfig, run_monte_carlo, evolve, compute_fitness
from .diagnostics import (
    convergence_analysis, sensitivity_analysis, 
    deterministic_baseline, compare_to_baseline,
    ga_hyperparameter_report, safe_eval_expr
)

__all__ = [
    "DomainConfig", "run_monte_carlo", "evolve", "compute_fitness",
    "convergence_analysis", "sensitivity_analysis",
    "deterministic_baseline", "compare_to_baseline",
    "ga_hyperparameter_report", "safe_eval_expr",
]
__version__ = "3.0.0"

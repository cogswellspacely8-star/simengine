"""SimEngine v2 — Universal Simulation Kernel + Diagnostics."""
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
__version__ = "2.1.0"

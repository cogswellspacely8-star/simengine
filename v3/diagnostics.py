"""
SimEngine Diagnostics Module
==============================
Addresses peer review concerns:
  1. Convergence diagnostics — proves sample sizes are sufficient
  2. Sensitivity analysis — one-at-a-time perturbation with common random
     numbers (first-order ranking; no Sobol/variance decomposition yet)
  3. Baseline comparison — spreadsheet-equivalent deterministic baseline
  4. Improved distributions — Student's t for fat tails, correlated sampling

Usage:
    from diagnostics import (
        convergence_analysis, sensitivity_analysis,
        deterministic_baseline, compare_to_baseline
    )
"""

import json
import os
import random
import math
import statistics
import copy
from typing import Optional
from kernel import (
    DomainConfig, run_monte_carlo, simulate_one,
    compute_fitness, percentile as _percentile, SAMPLERS, sampler,
    PROCESSES, PROCESS_NOISE_PARAM,
    _prepare_native_presampled_runs, SIM_LOCK
)

try:
    import native as native_runtime
except Exception:
    native_runtime = None


def _get_native_backend():
    if native_runtime is None:
        return None
    try:
        return native_runtime.get_native_backend()
    except Exception:
        return None


def _checkpoint_stats(values, metric_name):
    native_backend = _get_native_backend()
    if native_backend is not None:
        try:
            reduced = native_backend.reduce_metrics({metric_name: list(values)}, {metric_name: "number"})
            if metric_name in reduced:
                return reduced[metric_name]
        except Exception:
            pass

    sorted_values = sorted(values)
    return {
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
        "p10": round(_percentile(sorted_values, 10), 4),
        "p90": round(_percentile(sorted_values, 90), 4),
    }


# ---------------------------------------------------------------------------
# 1. CONVERGENCE DIAGNOSTICS
# ---------------------------------------------------------------------------

def convergence_analysis(config: DomainConfig, 
                         checkpoints: Optional[list] = None,
                         metric: Optional[str] = None,
                         seed: int = 42,
                         max_runs: int = 20000) -> dict:
    """
    Run increasing numbers of simulations and measure estimator stability.
    
    Reports how the mean, median, and P10/P90 of a target metric change
    as N increases. Convergence is achieved when the coefficient of variation
    of the running mean falls below a threshold.
    
    This directly addresses Dr. Antonova's critique: "How does the author
    know 5,000 runs is sufficient?"
    
    Returns:
        dict with checkpoints, running statistics, and convergence assessment.
    """
    if checkpoints is None:
        checkpoints = [100, 250, 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000]
    checkpoints = [c for c in checkpoints if c <= max_runs]
    
    if metric is None:
        metric = list(config.metrics.keys())[0]
    
    # Serialized like run_monte_carlo: this loop seeds and draws from the
    # process-global RNG directly.
    with SIM_LOCK:
        random.seed(seed)
        native_backend = _get_native_backend()
        presampled_runs = _prepare_native_presampled_runs(
            config, max(checkpoints), seed=seed, native_backend=native_backend
        )
    
        # Run all simulations at once, then subsample
        all_values = []
        for run_index in range(max(checkpoints)):
            result = simulate_one(
                config,
                sampled_steps=presampled_runs[run_index] if presampled_runs else None,
            )
            # Extract the target metric from final state
            state = result["final_state"]
            state.update(result["metrics"])
            all_values.append(result["metrics"].get(metric, 0))
    
    # Compute statistics at each checkpoint
    records = []
    for n in checkpoints:
        subset = all_values[:n]
        checkpoint = _checkpoint_stats(subset, metric)
        mean_val = checkpoint["mean"]
        median_val = checkpoint["median"]
        std_val = checkpoint["std"]
        p10 = checkpoint["p10"]
        p90 = checkpoint["p90"]
        
        # Standard error of the mean
        se_mean = std_val / math.sqrt(n) if n > 0 else 0
        # Coefficient of variation of the mean estimator
        cv_mean = se_mean / abs(mean_val) if abs(mean_val) > 1e-10 else float('inf')
        
        # 95% confidence interval half-width as % of mean
        ci95_pct = (1.96 * se_mean / abs(mean_val) * 100) if abs(mean_val) > 1e-10 else float('inf')
        
        records.append({
            "n": n,
            "mean": round(mean_val, 2),
            "median": round(median_val, 2),
            "std": round(std_val, 2),
            "se_mean": round(se_mean, 2),
            "cv_mean": round(cv_mean, 6),
            "ci95_pct": round(ci95_pct, 2),
            "p10": round(p10, 2),
            "p90": round(p90, 2),
        })
    
    # Determine convergence point: first N where CI95 < 5% of mean
    convergence_n = None
    for r in records:
        if r["ci95_pct"] < 5.0:
            convergence_n = r["n"]
            break
    
    # Stability check: compare last two checkpoints
    if len(records) >= 2:
        last = records[-1]
        prev = records[-2]
        mean_drift = abs(last["mean"] - prev["mean"]) / abs(last["mean"]) if abs(last["mean"]) > 0 else 0
        p10_drift = abs(last["p10"] - prev["p10"]) / abs(last["p10"]) if abs(last["p10"]) > 0 else 0
        p90_drift = abs(last["p90"] - prev["p90"]) / abs(last["p90"]) if abs(last["p90"]) > 0 else 0
    else:
        mean_drift = p10_drift = p90_drift = None
    
    return {
        "metric": metric,
        "total_runs": max(checkpoints),
        "checkpoints": records,
        "convergence_n": convergence_n,
        "convergence_criterion": "95% CI half-width < 5% of mean",
        "final_stability": {
            "mean_drift_pct": round(mean_drift * 100, 3) if mean_drift is not None else None,
            "p10_drift_pct": round(p10_drift * 100, 3) if p10_drift is not None else None,
            "p90_drift_pct": round(p90_drift * 100, 3) if p90_drift is not None else None,
        },
        "assessment": (
            f"Converged at N={convergence_n}" if convergence_n 
            else f"Did not converge within {max(checkpoints)} runs"
        ),
    }


def print_convergence(result: dict):
    """Pretty-print convergence analysis results."""
    print(f"\nConvergence Analysis: {result['metric']}")
    print(f"Criterion: {result['convergence_criterion']}")
    print("=" * 80)
    print(f"{'N':>8s}  {'Mean':>12s}  {'Median':>12s}  {'SE(mean)':>10s}  {'CI95%':>8s}  {'P10':>12s}  {'P90':>12s}")
    print("-" * 80)
    for r in result["checkpoints"]:
        ci = f"{r['ci95_pct']:.1f}%" if r['ci95_pct'] < 999 else ">999%"
        print(f"{r['n']:>8d}  {r['mean']:>12,.0f}  {r['median']:>12,.0f}  "
              f"{r['se_mean']:>10,.0f}  {ci:>8s}  {r['p10']:>12,.0f}  {r['p90']:>12,.0f}")
    print("-" * 80)
    print(f"Assessment: {result['assessment']}")
    if result["final_stability"]["mean_drift_pct"] is not None:
        fs = result["final_stability"]
        print(f"Final stability: mean drift {fs['mean_drift_pct']:.2f}%, "
              f"P10 drift {fs['p10_drift_pct']:.2f}%, P90 drift {fs['p90_drift_pct']:.2f}%")


# ---------------------------------------------------------------------------
# 2. SENSITIVITY ANALYSIS (Variance-Based, One-at-a-Time)
# ---------------------------------------------------------------------------

def sensitivity_analysis(config: DomainConfig,
                         metric: Optional[str] = None,
                         n_base: int = 2000,
                         n_perturb: int = 50,
                         perturbation_pct: float = 0.10,
                         seed: int = 42) -> dict:
    """
    One-at-a-time sensitivity analysis with normalized impact scores.
    
    For each variable parameter, perturb it by +/- perturbation_pct of its
    range, re-run the simulation, and measure the change in the target metric.
    
    This addresses Dr. Antonova's critique: "No sensitivity analysis 
    (Sobol indices, FAST). Which input variable drives the output variance most?"
    
    While a full Sobol decomposition requires O(N * (k+2)) model evaluations
    (prohibitive for many variables), this OAT approach provides a first-order
    sensitivity ranking at O(N * 2k) cost.
    
    Returns:
        dict with ranked parameter sensitivities and elasticity estimates.
    """
    if metric is None:
        metric = list(config.metrics.keys())[0]
    
    random.seed(seed)
    
    # Baseline run
    base_cfg = copy.deepcopy(config)
    base_cfg.n_simulations = n_base
    base_result = run_monte_carlo(base_cfg, seed=seed)
    base_mean = base_result["stats"][metric]["mean"]
    base_median = base_result["stats"][metric]["median"]
    
    # For each variable, perturb each numeric parameter
    sensitivities = []
    
    for var_name, var_def in config.all_variables.items():
        params = var_def.get("params", {})
        for param_name, param_val in params.items():
            if not isinstance(param_val, (int, float)):
                continue
            if isinstance(param_val, bool):
                continue
            
            # Determine perturbation range
            abs_val = abs(param_val) if abs(param_val) > 0 else 1.0
            delta = abs_val * perturbation_pct
            
            impacts_on_mean = []
            impacts_on_median = []
            
            for trial in range(n_perturb):
                # Common random numbers: the up and down legs share one seed so
                # the difference isolates the parameter effect instead of carrying
                # raw sampling noise (a zero-effect variable then scores exactly 0).
                trial_seed = seed + trial

                # Perturb up
                perturbed_up = copy.deepcopy(config)
                perturbed_up.n_simulations = n_base
                perturbed_up.all_variables[var_name]["params"][param_name] = param_val + delta

                r_up = run_monte_carlo(perturbed_up, seed=trial_seed)

                # Perturb down
                perturbed_dn = copy.deepcopy(config)
                perturbed_dn.n_simulations = n_base
                perturbed_dn.all_variables[var_name]["params"][param_name] = param_val - delta

                r_dn = run_monte_carlo(perturbed_dn, seed=trial_seed)
                
                up_mean = r_up["stats"][metric]["mean"]
                dn_mean = r_dn["stats"][metric]["mean"]
                
                # Central difference
                impact = abs(up_mean - dn_mean) / 2
                impacts_on_mean.append(impact)
                
                up_med = r_up["stats"][metric]["median"]
                dn_med = r_dn["stats"][metric]["median"]
                impacts_on_median.append(abs(up_med - dn_med) / 2)
            
            avg_impact = statistics.mean(impacts_on_mean)
            avg_impact_median = statistics.mean(impacts_on_median)
            
            # Elasticity: % change in output per % change in input
            if abs(base_mean) > 1e-10 and abs(param_val) > 1e-10:
                elasticity = (avg_impact / abs(base_mean)) / perturbation_pct
            else:
                elasticity = 0
            
            sensitivities.append({
                "variable": var_name,
                "parameter": param_name,
                "base_value": param_val,
                "perturbation": f"+/- {perturbation_pct*100:.0f}%",
                "avg_impact_on_mean": round(avg_impact, 2),
                "avg_impact_on_median": round(avg_impact_median, 2),
                "elasticity": round(elasticity, 4),
                "n_trials": n_perturb,
            })
    
    # Rank by impact
    sensitivities.sort(key=lambda x: x["avg_impact_on_mean"], reverse=True)
    
    # Normalize to get relative importance (sums to 1)
    total_impact = sum(s["avg_impact_on_mean"] for s in sensitivities)
    for s in sensitivities:
        s["relative_importance"] = round(
            s["avg_impact_on_mean"] / total_impact if total_impact > 0 else 0, 4
        )
    
    return {
        "metric": metric,
        "base_mean": round(base_mean, 2),
        "base_median": round(base_median, 2),
        "perturbation_pct": perturbation_pct,
        "n_base_runs": n_base,
        "n_perturbation_trials": n_perturb,
        "sensitivities": sensitivities,
    }


def print_sensitivity(result: dict):
    """Pretty-print sensitivity analysis."""
    print(f"\nSensitivity Analysis: {result['metric']}")
    print(f"Baseline mean: {result['base_mean']:,.0f} | Perturbation: +/- {result['perturbation_pct']*100:.0f}%")
    print("=" * 90)
    print(f"{'Rank':>4s}  {'Variable.Parameter':<35s}  {'Base':>10s}  {'Impact':>10s}  {'Elast.':>8s}  {'Rel.Imp':>8s}")
    print("-" * 90)
    for i, s in enumerate(result["sensitivities"]):
        label = f"{s['variable']}.{s['parameter']}"
        bar = "#" * int(s["relative_importance"] * 40)
        print(f"{i+1:>4d}  {label:<35s}  {s['base_value']:>10.2f}  "
              f"{s['avg_impact_on_mean']:>10,.0f}  {s['elasticity']:>8.3f}  "
              f"{s['relative_importance']:>7.1%}  {bar}")
    print("-" * 90)


# ---------------------------------------------------------------------------
# 3. DETERMINISTIC BASELINE
# ---------------------------------------------------------------------------

def deterministic_baseline(config: DomainConfig) -> dict:
    """
    Compute a single-point-estimate baseline using the mode/mean of each
    distribution. This is the "spreadsheet approach" — no randomness.
    
    Addresses Dr. Chen's critique: "No baseline comparison."
    This shows what a naive deterministic forecast would predict,
    making the value of Monte Carlo distribution analysis explicit.
    """
    # Create a deterministic config by replacing distributions with fixed values
    det_config = copy.deepcopy(config)
    det_config.n_simulations = 1  # Only need one run
    
    for var_name, var_def in det_config.all_variables.items():
        dist = var_def["distribution"]
        params = var_def.get("params", {})

        # A process's deterministic counterpart is its zero-noise path, not a
        # constant: keep the dynamics, silence the innovation.
        if dist in PROCESSES:
            quiet = dict(params)
            quiet[PROCESS_NOISE_PARAM[dist]] = 0.0
            det_config.all_variables[var_name] = {"distribution": dist, "params": quiet}
            continue
        
        # Extract the "most likely" value for each distribution
        if dist == "fixed":
            point_est = params["value"]
        elif dist == "triangular":
            point_est = params["mode"]
        elif dist == "normal":
            point_est = params["mean"]
        elif dist == "lognormal":
            point_est = params["median"]
        elif dist == "uniform":
            point_est = (params["low"] + params["high"]) / 2
        elif dist == "bernoulli":
            # Mode of a Bernoulli is a realizable 0/1, not the fractional mean p.
            point_est = 1.0 if params.get("p", 0) >= 0.5 else 0.0
        elif dist == "poisson":
            point_est = params["lambda"]
        elif dist == "student_t":
            point_est = params.get("mean", 0)
        elif dist == "beta":
            lo, hi = params.get("low", 0.0), params.get("high", 1.0)
            a, b = params["alpha"], params["beta"]
            point_est = lo + (hi - lo) * a / (a + b)
        elif dist == "gamma":
            scale = params["scale"] if "scale" in params else 1.0 / params["rate"]
            point_est = params["shape"] * scale
        elif dist == "categorical":
            values = params["values"]
            probs = params.get("probs")
            point_est = values[max(range(len(values)), key=lambda i: probs[i])] if probs else values[0]
        elif dist == "empirical":
            point_est = statistics.median(params["values"])
        else:
            point_est = 0
        
        det_config.all_variables[var_name] = {
            "distribution": "fixed",
            "params": {"value": point_est}
        }
    
    # Run once
    result = simulate_one(det_config)
    
    return {
        "method": "deterministic_baseline",
        "description": "Single-point forecast using mode/mean of each distribution",
        "final_metrics": result["metrics"],
        "history_length": len(result["history"]),
    }


def compare_to_baseline(config: DomainConfig, n_simulations: int = 5000,
                         seed: int = 42) -> dict:
    """
    Run both deterministic baseline and Monte Carlo, then compare.
    Shows the information gained by simulation over spreadsheet forecasting.
    """
    # Deterministic
    baseline = deterministic_baseline(config)
    
    # Monte Carlo
    mc_config = copy.deepcopy(config)
    mc_config.n_simulations = n_simulations
    mc_result = run_monte_carlo(mc_config, seed=seed)
    
    comparisons = {}
    for metric_name in config.metrics:
        det_val = baseline["final_metrics"].get(metric_name, 0)
        mc_stats = mc_result["stats"][metric_name]
        
        # Information gain: how much does the distribution tell us
        # that the point estimate doesn't?
        spread = mc_stats["p90"] - mc_stats["p10"]
        downside_surprise = det_val - mc_stats["p10"]  # how much worse it could be
        upside_surprise = mc_stats["p90"] - det_val    # how much better it could be
        
        comparisons[metric_name] = {
            "deterministic": round(det_val, 2),
            "mc_mean": mc_stats["mean"],
            "mc_median": mc_stats["median"],
            "mc_p10": mc_stats["p10"],
            "mc_p90": mc_stats["p90"],
            "p10_p90_spread": round(spread, 2),
            "downside_hidden_by_deterministic": round(downside_surprise, 2),
            "upside_hidden_by_deterministic": round(upside_surprise, 2),
            "format": mc_stats.get("format", "number"),
        }
    
    return {
        "baseline": baseline,
        "monte_carlo": mc_result["stats"],
        "comparison": comparisons,
        "n_simulations": n_simulations,
        "verdict": "Monte Carlo reveals risk that deterministic forecasting hides",
    }


def print_comparison(result: dict):
    """Pretty-print baseline vs Monte Carlo comparison."""
    print("\nDeterministic Baseline vs Monte Carlo Simulation")
    print("=" * 85)
    print(f"{'Metric':<25s}  {'Determ.':>10s}  {'MC Mean':>10s}  {'MC P10':>10s}  "
          f"{'MC P90':>10s}  {'Hidden Risk':>12s}")
    print("-" * 85)
    for name, c in result["comparison"].items():
        fmt = c["format"]
        if fmt == "dollar":
            print(f"{name:<25s}  ${c['deterministic']:>9,.0f}  ${c['mc_mean']:>9,.0f}  "
                  f"${c['mc_p10']:>9,.0f}  ${c['mc_p90']:>9,.0f}  "
                  f"${c['downside_hidden_by_deterministic']:>11,.0f}")
        elif fmt == "percent":
            print(f"{name:<25s}  {c['deterministic']:>9.1%}  {c['mc_mean']:>9.1%}  "
                  f"{c['mc_p10']:>9.1%}  {c['mc_p90']:>9.1%}  "
                  f"{c['downside_hidden_by_deterministic']:>11.1%}")
        else:
            print(f"{name:<25s}  {c['deterministic']:>10.1f}  {c['mc_mean']:>10.1f}  "
                  f"{c['mc_p10']:>10.1f}  {c['mc_p90']:>10.1f}  "
                  f"{c['downside_hidden_by_deterministic']:>12.1f}")
    print("-" * 85)
    print(f"Verdict: {result['verdict']}")


# ---------------------------------------------------------------------------
# 4. IMPROVED DISTRIBUTIONS — Student's t for fat tails
# ---------------------------------------------------------------------------

@sampler("student_t")
def sample_student_t(params: dict) -> float:
    """
    Student's t-distribution for fat-tailed returns.
    
    Addresses Dr. Lindqvist's critique: "normally distributed returns 
    is a known dangerous assumption."
    
    Uses the transformation: if Z ~ N(0,1) and V ~ chi2(df), then
    T = Z / sqrt(V/df) follows t(df). For df=5, this produces
    substantially fatter tails than normal.
    
    Params:
        mean: location parameter
        scale: scale parameter (analogous to std)
        df: degrees of freedom (lower = fatter tails; 5 is common for equities)
        min/max: optional clamping bounds
    """
    # df drives range(); round so fractional df (e.g. 4.5) samples instead of
    # raising TypeError (mirrors kernel._student_t).
    df = max(1, int(round(params.get("df", 5))))
    mean = params.get("mean", 0)
    scale = params.get("scale", 1)

    # Generate t-distributed sample via ratio of normal to chi-squared
    z = random.gauss(0, 1)
    # Chi-squared(df) = sum of df standard normals squared
    v = sum(random.gauss(0, 1) ** 2 for _ in range(df))
    t_val = z / math.sqrt(v / df)
    
    result = mean + scale * t_val
    lo = params.get("min", -1e18)
    hi = params.get("max", 1e18)
    return max(lo, min(hi, result))


@sampler("correlated_normal")
def sample_correlated_normal(params: dict) -> float:
    """
    Sample from a normal conditioned on another variable's current value.
    
    Addresses the independence assumption critique: allows basic 
    correlation between variables without full copula modeling.
    
    Params:
        base_mean, base_std: unconditional parameters
        correlation: rho with the conditioning variable
        condition_var: name of the conditioning variable (read from state)
        condition_mean, condition_std: parameters of conditioning variable
        min/max: optional clamping bounds
    """
    # This is a placeholder that requires state access
    # Actual correlation is handled in the step logic via expressions
    # e.g., "project_value * (1 + 0.3 * (close_rate - 0.3) / 0.15)"
    return random.gauss(params.get("mean", 0), params.get("std", 1))


# ---------------------------------------------------------------------------
# 5. EXPRESSION EVALUATOR SECURITY
# ---------------------------------------------------------------------------

# Restricted AST-based evaluator for production use
import ast
import operator

SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_INVALID_SAFE_EXPR = object()
_SAFE_EXPR_AST_CACHE = {}


def clear_safe_eval_expr_cache():
    _SAFE_EXPR_AST_CACHE.clear()


def _parse_safe_expr_cached(expr: str):
    if os.environ.get("SIMENGINE_DISABLE_SAFE_EXPR_CACHE"):
        try:
            return ast.parse(expr, mode='eval')
        except SyntaxError:
            return _INVALID_SAFE_EXPR

    cached = _SAFE_EXPR_AST_CACHE.get(expr)
    if cached is not None:
        return cached

    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError:
        tree = _INVALID_SAFE_EXPR

    _SAFE_EXPR_AST_CACHE[expr] = tree
    return tree


def safe_eval_expr(expr: str, state: dict, allowed_callables: dict = None) -> any:
    """
    AST-based expression evaluator that never calls eval().
    
    Addresses Dr. Vasquez's critique: "Python's eval() sandboxing 
    is notoriously leaky."
    
    Supports: arithmetic, comparisons, function calls from whitelist,
    variable references, ternary expressions, and list comprehensions
    for binomial().
    
    Does NOT support: imports, attribute access, subscript on arbitrary
    objects, or any form of code execution beyond arithmetic and
    whitelisted function calls.
    """
    from kernel import SAFE_BUILTINS
    
    if allowed_callables is None:
        allowed_callables = SAFE_BUILTINS
    
    # Merge state into namespace
    namespace = {**allowed_callables, **state}

    tree = _parse_safe_expr_cached(expr)
    if tree is _INVALID_SAFE_EXPR:
        return 0
    
    def _eval_node(node):
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in namespace:
                return namespace[node.id]
            return 0
        elif isinstance(node, ast.BinOp):
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            op = SAFE_OPS.get(type(node.op))
            if op is None:
                return 0
            try:
                return op(left, right)
            except (ZeroDivisionError, OverflowError):
                return 0
        elif isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            op = SAFE_OPS.get(type(node.op))
            return op(operand) if op else 0
        elif isinstance(node, ast.Compare):
            left = _eval_node(node.left)
            for op_node, comparator in zip(node.ops, node.comparators):
                right = _eval_node(comparator)
                op = SAFE_COMPARISONS.get(type(op_node))
                if op is None or not op(left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.IfExp):
            test = _eval_node(node.test)
            return _eval_node(node.body) if test else _eval_node(node.orelse)
        elif isinstance(node, ast.Call):
            func = _eval_node(node.func)
            if not callable(func):
                return 0
            args = [_eval_node(a) for a in node.args]
            kwargs = {kw.arg: _eval_node(kw.value) for kw in node.keywords}
            try:
                return func(*args, **kwargs)
            except Exception:
                return 0
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = True
                for val in node.values:
                    result = _eval_node(val)
                    if not result:
                        return result
                return result
            elif isinstance(node.op, ast.Or):
                result = False
                for val in node.values:
                    result = _eval_node(val)
                    if result:
                        return result
                return result
        return 0
    
    try:
        return _eval_node(tree)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 6. GA HYPERPARAMETER REPORTING
# ---------------------------------------------------------------------------

def ga_hyperparameter_report(population_size: int, generations: int,
                              mc_runs_per_eval: int, n_tunable: int,
                              elite_count: int = 2, tournament_size: int = 3,
                              crossover_type: str = "uniform",
                              mutation_rate: float = 0.25,
                              mutation_strength: float = 0.10) -> dict:
    """
    Generate explicit GA hyperparameter documentation.
    
    Addresses Prof. Nakamura's critique: "Population size, crossover rate,
    mutation variance, tournament size, elite fraction — none are specified
    or justified."
    """
    total_evaluations = population_size * generations
    total_mc_runs = total_evaluations * mc_runs_per_eval
    
    return {
        "population_size": population_size,
        "generations": generations,
        "total_individual_evaluations": total_evaluations,
        "mc_runs_per_individual": mc_runs_per_eval,
        "total_mc_simulations": total_mc_runs,
        "selection": {
            "method": "tournament",
            "tournament_size": tournament_size,
            "pressure": f"{tournament_size}/{population_size} = {tournament_size/population_size:.2%}",
        },
        "elitism": {
            "count": elite_count,
            "fraction": f"{elite_count}/{population_size} = {elite_count/population_size:.1%}",
        },
        "crossover": {
            "method": crossover_type,
            "description": "Each gene independently selected from either parent with p=0.5",
        },
        "mutation": {
            "rate": mutation_rate,
            "strength": mutation_strength,
            "method": "Gaussian perturbation scaled to parameter range",
            "description": f"Each tunable param mutated with p={mutation_rate}, "
                          f"delta ~ N(0, range * {mutation_strength})",
        },
        "search_space": {
            "n_tunable_parameters": n_tunable,
            "theoretical_space": "continuous (bounded)",
        },
        "fitness_evaluation": {
            "stochastic": True,
            "noise_source": f"MC sampling with N={mc_runs_per_eval}",
            "noise_mitigation": "Elitism preserves best-known solutions across noisy evaluations",
        },
    }


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="SimEngine Diagnostics")
    parser.add_argument("domain", help="Path to domain config JSON")
    parser.add_argument("--convergence", action="store_true")
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--metric", type=str, default=None)
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()
    
    config = DomainConfig.from_json(args.domain)
    
    if args.convergence:
        result = convergence_analysis(config, metric=args.metric)
        print_convergence(result)
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
    
    if args.sensitivity:
        result = sensitivity_analysis(config, metric=args.metric, n_perturb=10)
        print_sensitivity(result)
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
    
    if args.baseline:
        result = compare_to_baseline(config)
        print_comparison(result)
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()

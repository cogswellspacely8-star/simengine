"""
SimEngine v3 — Restructured Kernel
=====================================
Key changes from v2:
  1. Schema separates: parameters, controls, exogenous, observations
  2. CVaR + chance constraints on the optimizer
  3. Experiment manifest for reproducibility
  4. Calibration metadata per variable

Design informed by:
  - Sonnet 4.6 panel review (8 reviewers, March 2026)
  - ChatGPT deep research counterpaper (March 2026)
  - ChatGPT-4o critique (March 2026)
"""

import json, random, math, copy, time, statistics, sys, hashlib, os
from dataclasses import dataclass, field
from typing import Any, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

try:
    import native as native_runtime
except Exception:
    native_runtime = None

# ---------------------------------------------------------------------------
# Distribution Samplers
# ---------------------------------------------------------------------------
SAMPLERS = {}
def sampler(name):
    def dec(fn):
        SAMPLERS[name] = fn
        return fn
    return dec

@sampler("fixed")
def _fixed(p): return p["value"]

@sampler("uniform")
def _uniform(p): return random.uniform(p["low"], p["high"])

@sampler("triangular")
def _triangular(p): return random.triangular(p["low"], p["high"], p["mode"])

@sampler("normal")
def _normal(p):
    v = random.gauss(p["mean"], p["std"])
    return max(p.get("min", -1e18), min(p.get("max", 1e18), v))

@sampler("lognormal")
def _lognormal(p):
    v = random.lognormvariate(math.log(p["median"]), p["spread"])
    return max(p.get("min", 0), min(p.get("max", 1e18), v))

@sampler("bernoulli")
def _bernoulli(p): return 1.0 if random.random() < p["p"] else 0.0

@sampler("poisson")
def _poisson(p):
    L = math.exp(-p["lambda"])
    k, pr = 0, 1.0
    while pr > L:
        k += 1; pr *= random.random()
    return float(k - 1)

@sampler("student_t")
def _student_t(p):
    df = p.get("df", 5)
    z = random.gauss(0, 1)
    v = sum(random.gauss(0, 1)**2 for _ in range(df))
    t = z / math.sqrt(v / df) if v > 0 else z
    result = p.get("mean", 0) + p.get("scale", 1) * t
    return max(p.get("min", -1e18), min(p.get("max", 1e18), result))

def _binomial(n, p):
    trials = max(0, int(round(n)))
    probability = _clamp(float(p), 0.0, 1.0)

    if not os.environ.get("SIMENGINE_DISABLE_NATIVE_EXPR_SAMPLING"):
        native_backend = _get_native_backend()
        if native_backend is not None and hasattr(native_backend, "sample_binomial"):
            try:
                return int(
                    native_backend.sample_binomial(
                        trials, probability, random.getrandbits(63)
                    )
                )
            except Exception:
                pass

    return sum(1 for _ in range(trials) if random.random() < probability)

def _clamp(v, lo, hi): return max(lo, min(hi, v))

# ---------------------------------------------------------------------------
# Cholesky Decomposition for Correlated Sampling
# ---------------------------------------------------------------------------
def cholesky(matrix):
    """Cholesky decomposition of a positive-definite matrix. Returns lower triangular L."""
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                val = matrix[i][i] - s
                L[i][j] = math.sqrt(max(0, val))
            else:
                L[i][j] = (matrix[i][j] - s) / L[j][j] if L[j][j] > 0 else 0
    return L

def generate_correlated_normals(L, n):
    """Generate n correlated standard normals using Cholesky factor L."""
    z = [random.gauss(0, 1) for _ in range(n)]
    return [sum(L[i][j] * z[j] for j in range(i + 1)) for i in range(n)]

def normal_cdf_inv_approx(p):
    """Approximate inverse normal CDF (Beasley-Springer-Moro algorithm)."""
    if p <= 0: return -4.0
    if p >= 1: return 4.0
    if p == 0.5: return 0.0
    # Rational approximation
    t = math.sqrt(-2.0 * math.log(min(p, 1 - p)))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    result = t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t)
    return result if p > 0.5 else -result

def normal_cdf_approx(x):
    """Approximate standard normal CDF."""
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    p = d * math.exp(-x * x / 2.0) * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    return 1.0 - p if x > 0 else p

def apply_correlation_to_sample(base_value, var_def, correlated_z):
    """Transform a correlated standard normal into the variable's distribution."""
    # Convert correlated Z to uniform via normal CDF, then to target distribution
    u = normal_cdf_approx(correlated_z)  # uniform [0,1]
    dist = var_def.get("distribution", "fixed")
    params = var_def.get("params", {})

    if dist == "fixed":
        return params.get("value", 0)
    elif dist == "uniform":
        lo, hi = params.get("low", 0), params.get("high", 1)
        return lo + u * (hi - lo)
    elif dist == "triangular":
        lo, mode, hi = params.get("low", 0), params.get("mode", 0.5), params.get("high", 1)
        fc = (mode - lo) / (hi - lo) if hi > lo else 0.5
        if u < fc:
            return lo + math.sqrt(u * (hi - lo) * (mode - lo))
        else:
            return hi - math.sqrt((1 - u) * (hi - lo) * (hi - mode))
    elif dist == "normal":
        mean, std = params.get("mean", 0), params.get("std", 1)
        v = mean + std * correlated_z
        return max(params.get("min", -1e18), min(params.get("max", 1e18), v))
    elif dist == "lognormal":
        median, spread = params.get("median", 1), params.get("spread", 0.5)
        v = median * math.exp(spread * correlated_z)
        return max(params.get("min", 0), min(params.get("max", 1e18), v))
    elif dist == "bernoulli":
        return 1.0 if u < params.get("p", 0.5) else 0.0
    elif dist == "poisson":
        # Use inverse CDF for Poisson
        lam = params.get("lambda", 1)
        k, p_cum = 0, math.exp(-lam)
        while u > p_cum and k < 100:
            k += 1
            p_cum += math.exp(-lam + k * math.log(lam) - sum(math.log(i) for i in range(1, k + 1)))
        return float(k)
    else:
        return base_value

SAFE_BUILTINS = {
    "min": min, "max": max, "abs": abs, "round": round,
    "sum": sum, "len": len, "int": int, "float": float,
    "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
    "ceil": math.ceil, "floor": math.floor, "pow": pow,
    "random": random.random, "gauss": random.gauss,
    "binomial": _binomial, "clamp": _clamp,
    "range": range, "True": True, "False": False,
}

NATIVE_BATCH_SAMPLER_DISTRIBUTIONS = {
    "fixed", "uniform", "triangular", "normal",
    "lognormal", "bernoulli", "poisson", "student_t",
}

_INVALID_EXPR = object()
_COMPILED_EXPR_CACHE = {}

def clear_eval_expr_cache():
    _COMPILED_EXPR_CACHE.clear()


def _compile_expr_cached(expr):
    if os.environ.get("SIMENGINE_DISABLE_EXPR_CACHE"):
        try:
            return compile(expr, "<simengine-expr>", "eval")
        except Exception:
            return _INVALID_EXPR

    cached = _COMPILED_EXPR_CACHE.get(expr)
    if cached is not None:
        return cached

    try:
        compiled = compile(expr, "<simengine-expr>", "eval")
    except Exception:
        compiled = _INVALID_EXPR

    _COMPILED_EXPR_CACHE[expr] = compiled
    return compiled


def eval_expr(expr, state):
    compiled = _compile_expr_cached(expr)
    if compiled is _INVALID_EXPR:
        return 0
    try:
        return eval(compiled, {"__builtins__": SAFE_BUILTINS}, state)
    except:
        return 0

def sample_var(var_def, state):
    params = {}
    for k, v in var_def.get("params", {}).items():
        if isinstance(v, str) and v.startswith("$"):
            params[k] = state.get(v[1:], 0)
        else:
            params[k] = v
    return SAMPLERS[var_def["distribution"]](params)

# ---------------------------------------------------------------------------
# Experiment Manifest
# ---------------------------------------------------------------------------
def make_manifest(config_path, n_sims, seed, extra=None):
    """Addresses reproducibility critique: every run is traceable."""
    config_text = json.dumps(config_path) if isinstance(config_path, dict) else open(config_path).read()
    return {
        "config_hash": hashlib.sha256(config_text.encode()).hexdigest()[:16],
        "n_simulations": n_sims,
        "seed": seed,
        "kernel_version": "3.0.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "extra": extra or {},
    }

# ---------------------------------------------------------------------------
# Domain Config v3 — Restructured Schema
# ---------------------------------------------------------------------------
class DomainConfig:
    """
    v3 schema separates variables into four categories:
      parameters:  uncertain values updated by evidence (close rate, market return)
      controls:    decisions the operator makes (pricing, effort allocation)
      exogenous:   external shocks the operator cannot control (market crashes, weather)
      observations: what you can actually measure (revenue received, offers gotten)
    
    Plus: calibration metadata per variable, safety constraints, experiment manifest.
    """
    def __init__(self, data):
        self.raw = data
        self.name = data.get("name", "unnamed")
        self.description = data.get("description", "")
        self.n_simulations = data.get("n_simulations", 5000)
        self.n_steps = data.get("n_steps", 12)
        self.step_label = data.get("step_label", "step")
        self.seed = data.get("seed")
        
        # v3: four variable categories (all sampled the same way but semantically distinct)
        self.parameters = data.get("parameters", {})
        self.controls = data.get("controls", {})
        self.exogenous = data.get("exogenous", {})
        
        # Backward compat: merge old "variables" into parameters
        if "variables" in data and not self.parameters:
            self.parameters = data["variables"]
        
        # All variables merged for sampling
        self.all_variables = {}
        self.all_variables.update(self.parameters)
        self.all_variables.update(self.controls)
        self.all_variables.update(self.exogenous)
        
        self.step_logic = data.get("step_logic", [])
        self.accumulators = data.get("accumulators", {})
        self.metrics = data.get("metrics", {})
        self.initial_state = data.get("initial_state", {})
        
        # v3: safety constraints
        self.safety = data.get("safety", {})
        
        # v3: fitness with optional CVaR
        self.fitness = data.get("fitness", {})
        
        # v3: tunable (only controls and some parameters)
        self.tunable = data.get("tunable", [])
        
        # v3: calibration metadata
        self.calibration = data.get("calibration", {})

        # v3.1: correlations between variables
        # Format: [{"vars": ["var_a", "var_b"], "rho": 0.6}, ...]
        self.correlations = data.get("correlations", [])
        self._corr_vars = []
        self._corr_L = None
        if self.correlations:
            # Build correlation matrix and Cholesky factor
            corr_var_set = set()
            for c in self.correlations:
                for v in c.get("vars", []):
                    corr_var_set.add(v)
            self._corr_vars = sorted(corr_var_set)
            n = len(self._corr_vars)
            idx = {v: i for i, v in enumerate(self._corr_vars)}
            matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
            for c in self.correlations:
                vs = c.get("vars", [])
                rho = c.get("rho", 0)
                if len(vs) == 2 and vs[0] in idx and vs[1] in idx:
                    i, j = idx[vs[0]], idx[vs[1]]
                    matrix[i][j] = rho
                    matrix[j][i] = rho
            self._corr_L = cholesky(matrix)
    
    @classmethod
    def from_json(cls, path):
        with open(path) as f:
            return cls(json.load(f))
    
    @classmethod
    def from_dict(cls, d):
        return cls(d)
    
    def to_dict(self):
        return self.raw

# ---------------------------------------------------------------------------
# Simulation Runner
# ---------------------------------------------------------------------------
def simulate_one(config, sampled_steps=None):
    state = dict(config.initial_state)
    state["_step"] = 0
    for acc in config.accumulators:
        if acc not in state:
            state[acc] = 0.0
    
    history = []
    for step in range(1, config.n_steps + 1):
        state["_step"] = step
        step_rec = {"_step": step}

        # Generate correlated samples if correlations defined
        corr_samples = {}
        if config._corr_L and config._corr_vars:
            z_corr = generate_correlated_normals(config._corr_L, len(config._corr_vars))
            for i, vname in enumerate(config._corr_vars):
                if vname in config.all_variables:
                    corr_samples[vname] = z_corr[i]

        for vname, vdef in config.all_variables.items():
            precomputed = sampled_steps.get(vname) if sampled_steps else None
            if precomputed is not None and (step - 1) < len(precomputed):
                state[vname] = precomputed[step - 1]
            elif vname in corr_samples:
                state[vname] = apply_correlation_to_sample(0, vdef, corr_samples[vname])
            else:
                state[vname] = sample_var(vdef, state)
            step_rec[vname] = state[vname]
        
        for logic in config.step_logic:
            target = logic["target"]
            if "expr" in logic:
                state[target] = eval_expr(logic["expr"], state)
            elif "sample" in logic:
                state[target] = sample_var(logic["sample"], state)
            step_rec[target] = state[target]
        
        for acc, expr in config.accumulators.items():
            state[acc] = eval_expr(expr, state)
            step_rec[acc] = state[acc]
        
        history.append(step_rec)
    
    final_metrics = {}
    for mname, mdef in config.metrics.items():
        final_metrics[mname] = eval_expr(mdef["expr"], state)
    
    return {"final_state": state, "metrics": final_metrics, "history": history}


def percentile(data, pct):
    if not data: return 0
    k = (len(data) - 1) * (pct / 100)
    f, c = math.floor(k), math.ceil(k)
    if f == c: return data[int(k)]
    return data[f] * (c - k) + data[c] * (k - f)


def _get_native_backend():
    if native_runtime is None:
        return None
    try:
        return native_runtime.get_native_backend()
    except Exception:
        return None


def _build_native_variable_plan(config):
    plan = {}
    for vname, vdef in config.all_variables.items():
        distribution = vdef.get("distribution")
        if distribution not in NATIVE_BATCH_SAMPLER_DISTRIBUTIONS:
            return None

        params = {}
        for key, value in vdef.get("params", {}).items():
            if isinstance(value, str) and value.startswith("$"):
                return None
            if not isinstance(value, (int, float)):
                return None
            params[key] = float(value)

        plan[vname] = {"distribution": distribution, "params": params}
    return plan


def _native_sampling_seed(seed):
    if seed is not None:
        return int(seed) & ((1 << 64) - 1)
    return random.getrandbits(63)


def _prepare_native_presampled_runs(config, n_runs, seed=None, native_backend=None):
    if os.environ.get("SIMENGINE_DISABLE_NATIVE_SAMPLING"):
        return None

    native_backend = native_backend or _get_native_backend()
    if native_backend is None or not hasattr(native_backend, "sample_variable_grid"):
        return None
    if config._corr_L or config._corr_vars:
        return None

    variable_plan = _build_native_variable_plan(config)
    if not variable_plan:
        return None

    try:
        sampled = native_backend.sample_variable_grid(
            variable_plan,
            config.n_steps,
            n_runs,
            _native_sampling_seed(seed),
        )
    except Exception:
        return None

    prepared = [dict() for _ in range(n_runs)]
    for vname, per_sim in sampled.items():
        if len(per_sim) != n_runs:
            return None
        for sim_index, per_step in enumerate(per_sim):
            if len(per_step) != config.n_steps:
                return None
            prepared[sim_index][vname] = per_step
    return prepared


def _metric_formats(config):
    return {mname: config.metrics[mname].get("format", "number") for mname in config.metrics}


def _compute_stats_python(all_metrics, metric_formats):
    stats = {}
    for mname, vals in all_metrics.items():
        if not vals:
            continue
        sv = sorted(vals)
        stats[mname] = {
            "mean": round(statistics.mean(vals), 2),
            "median": round(statistics.median(vals), 2),
            "std": round(statistics.stdev(vals), 2) if len(vals) > 1 else 0,
            "p10": round(percentile(sv, 10), 2),
            "p25": round(percentile(sv, 25), 2),
            "p75": round(percentile(sv, 75), 2),
            "p90": round(percentile(sv, 90), 2),
            "format": metric_formats.get(mname, "number"),
        }
    return stats


def _annotate_indicators(stats, all_metrics):
    """Tag indicator metrics with their event probability (`binary_prob`).

    A "100 if cond else 0" (or 0/1) metric yields per-run values of only 0 and
    100 (or 0 and 1); its median collapses to its mode, so a 32% chance shows as
    "most likely 0.0". The mean is the actual probability. Detected from the raw
    value SET — percentiles interpolate off-grid and miss tail / 50-50 / high
    rates — so this holds across the whole 0..1 band. Count metrics on a 0..N
    scale (value set not a subset of {0,100}/{0,1}) are deliberately untouched.
    """
    for mname, s in stats.items():
        if not isinstance(s, dict):
            continue
        vals = all_metrics.get(mname)
        if not vals:
            continue
        valset = set(vals)
        if len(valset) < 2:
            continue  # degenerate (all-true or all-false) — no informative probability
        if valset <= {0, 100}:
            s["binary_prob"] = round(sum(vals) / len(vals) / 100.0, 4)
        elif valset <= {0, 1}:
            s["binary_prob"] = round(sum(vals) / len(vals), 4)
    return stats


def indicator_probability(stat):
    """Event probability in (0, 1) for an indicator metric, else None.

    Reads `binary_prob`, set by `_annotate_indicators` from the raw value set
    (robust across all event rates). Consumed by the narrative + sim_ask CLI so
    they report a probability instead of the misleading median.
    """
    if not isinstance(stat, dict):
        return None
    p = stat.get("binary_prob")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and 0 < p < 1:
        return p
    return None


def _compute_trajectories_python(trajectory_samples):
    trajectories = {}
    for acc, steps in trajectory_samples.items():
        p10, p50, p90 = [], [], []
        for vals in steps:
            sorted_vals = sorted(vals)
            p10.append(round(percentile(sorted_vals, 10), 2))
            p50.append(round(percentile(sorted_vals, 50), 2))
            p90.append(round(percentile(sorted_vals, 90), 2))
        trajectories[acc] = {"p10": p10, "p50": p50, "p90": p90}
    return trajectories


# Chance-constraint condition keywords. Only "below"/"above" were recognized
# historically; every synonym silently fell through to greater-than, inverting
# the violation probability. These alias sets are the single source of truth
# (validation.py imports them to reject unknown keywords at design time).
# Inclusive operators (<=, >=) are treated as their strict family — the
# difference is measure-zero for continuous Monte Carlo metrics.
BELOW_CONDITIONS = frozenset({"below", "lt", "<", "less_than", "under", "lte", "<="})
ABOVE_CONDITIONS = frozenset({"above", "gt", ">", "greater_than", "exceeds", "gte", ">="})


def normalize_condition(condition):
    """Return 'below' or 'above' for a recognized keyword; raise on anything else."""
    cond = str(condition).strip().lower()
    if cond in BELOW_CONDITIONS:
        return "below"
    if cond in ABOVE_CONDITIONS:
        return "above"
    raise ValueError(
        f"Unknown chance-constraint condition {condition!r}; "
        f"use one of below/lt/< or above/gt/>"
    )


def _evaluate_safety_python(raw, safety_config):
    results = {"chance": [], "cvar": [], "all_passed": True}

    for cc in safety_config.get("chance_constraints", []):
        metric = cc["metric"]
        vals = raw.get(metric, [])
        if not vals:
            continue

        threshold = cc["threshold"]
        max_prob = cc["max_prob"]

        if normalize_condition(cc["condition"]) == "below":
            violations = sum(1 for v in vals if v < threshold)
        else:
            violations = sum(1 for v in vals if v > threshold)

        actual_prob = violations / len(vals)
        passed = actual_prob <= max_prob

        results["chance"].append({
            "metric": metric, "condition": cc["condition"],
            "threshold": threshold, "max_prob": max_prob,
            "actual_prob": round(actual_prob, 4),
            "passed": passed,
        })
        if not passed:
            results["all_passed"] = False

    for cv in safety_config.get("cvar_constraints", []):
        metric = cv["metric"]
        vals = raw.get(metric, [])
        if not vals:
            continue

        alpha = cv["alpha"]
        min_cvar = cv["min_cvar"]
        actual_cvar = compute_cvar(vals, alpha)
        passed = actual_cvar >= min_cvar

        results["cvar"].append({
            "metric": metric, "alpha": alpha,
            "min_cvar": min_cvar,
            "actual_cvar": round(actual_cvar, 2),
            "passed": passed,
        })
        if not passed:
            results["all_passed"] = False

    return results


def run_monte_carlo(config, seed=None, n_override=None):
    n = n_override or config.n_simulations
    if seed is not None:
        random.seed(seed)

    native_backend = _get_native_backend()
    presampled_runs = _prepare_native_presampled_runs(config, n, seed=seed, native_backend=native_backend)

    all_metrics = {m: [] for m in config.metrics}
    trajectory_samples = {acc: [[] for _ in range(config.n_steps)] for acc in config.accumulators}
    
    for run_index in range(n):
        r = simulate_one(config, sampled_steps=presampled_runs[run_index] if presampled_runs else None)
        for m, v in r["metrics"].items():
            all_metrics[m].append(v)
        for si, step in enumerate(r["history"]):
            for acc, per_step_values in trajectory_samples.items():
                per_step_values[si].append(step.get(acc, 0))

    metric_formats = _metric_formats(config)
    stats = None
    trajectories = None

    if native_backend is not None:
        try:
            stats = native_backend.reduce_metrics(all_metrics, metric_formats)
            trajectories = native_backend.compute_trajectories(trajectory_samples)
        except Exception:
            stats = None
            trajectories = None

    if stats is None:
        stats = _compute_stats_python(all_metrics, metric_formats)
    if trajectories is None:
        trajectories = _compute_trajectories_python(trajectory_samples)

    # Annotate indicator metrics with their event probability (works regardless
    # of whether stats came from the native or pure-Python reducer).
    _annotate_indicators(stats, all_metrics)

    return {
        "domain": config.name, "n_simulations": n,
        "stats": stats, "trajectories": trajectories,
        "raw_metrics": all_metrics,
    }

# ---------------------------------------------------------------------------
# CVaR / Chance Constraint Evaluation
# ---------------------------------------------------------------------------
def compute_cvar(values, alpha=0.05):
    """
    Conditional Value at Risk (Expected Shortfall) at level alpha.
    CVaR_alpha = mean of the worst alpha fraction of outcomes.
    
    For losses (lower = worse), sort ascending and take bottom alpha%.
    """
    sv = sorted(values)
    n_tail = max(1, int(len(sv) * alpha))
    tail = sv[:n_tail]
    return statistics.mean(tail)


def evaluate_safety(mc_result, safety_config):
    """
    Evaluate safety constraints against Monte Carlo results.
    
    safety_config format:
    {
      "chance_constraints": [
        {"metric": "annual_revenue", "condition": "below", "threshold": 60000, "max_prob": 0.15}
      ],
      "cvar_constraints": [
        {"metric": "final_cash", "alpha": 0.10, "min_cvar": -20000}
      ]
    }
    
    Returns dict of constraint evaluations with pass/fail.
    """
    raw = mc_result.get("raw_metrics", {})
    native_backend = _get_native_backend()
    if native_backend is not None:
        try:
            return native_backend.evaluate_safety(raw, safety_config)
        except Exception:
            pass
    return _evaluate_safety_python(raw, safety_config)

# ---------------------------------------------------------------------------
# Fitness with Safety Penalty
# ---------------------------------------------------------------------------
def compute_fitness(mc_result, fitness_def, safety_config=None, safety_result=None):
    """Fitness score with CVaR penalty for safety violations."""
    state = {}
    for mname, mstats in mc_result["stats"].items():
        for sname, sval in mstats.items():
            if isinstance(sval, (int, float)):
                state[f"{mname}_{sname}"] = sval
    
    # Base fitness from components
    total = 0
    for comp in fitness_def.get("components", []):
        score = eval_expr(comp["expr"], state)
        total += score * comp.get("weight", 1.0)
    
    # Safety penalty
    if safety_config:
        safety = safety_result if safety_result is not None else evaluate_safety(mc_result, safety_config)
        if not safety["all_passed"]:
            # Count violations and apply penalty
            n_violations = sum(1 for c in safety["chance"] if not c["passed"])
            n_violations += sum(1 for c in safety["cvar"] if not c["passed"])
            total *= max(0.1, 1.0 - 0.3 * n_violations)  # 30% penalty per violation
    
    return round(total, 2)

# ---------------------------------------------------------------------------
# Safe Evolutionary Optimizer (v3)
# ---------------------------------------------------------------------------
TUNABLE_CACHE = {}


def clear_tunable_cache():
    TUNABLE_CACHE.clear()


def _prepare_tunable_specs(tunable):
    cache_key = tuple(
        (
            param.get("path"),
            tuple(param.get("range", [])),
            bool(param.get("integer", False)),
            param.get("step"),
        )
        for param in tunable
    )
    cached = TUNABLE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    prepared = []
    for param in tunable:
        parts = tuple(param["path"].split("."))
        prepared.append({
            "path": param["path"],
            "parts": parts,
            "parents": parts[:-1],
            "leaf": parts[-1],
            "range": tuple(param["range"]),
            "integer": bool(param.get("integer", False)),
            "step": param.get("step"),
        })

    TUNABLE_CACHE[cache_key] = prepared
    return prepared


def _quantize(value, lo, hi, integer=False, step=None):
    """Clamp a candidate lever value to [lo, hi] and snap it to the grid the
    control actually lives on: a numeric `step`, integers, or (default) 4 dp.
    Without integer/step this is the historical round(value, 4) behavior."""
    value = max(lo, min(hi, value))
    if step:
        value = lo + round((value - lo) / step) * step
        value = max(lo, min(hi, value))
    if integer:
        return int(round(value))
    return round(value, 4)


def _resolve_parent(obj, parents):
    current = obj
    for part in parents:
        current = current[part]
    return current


def mutate_config(config_dict, tunable, rate=0.3, strength=0.15):
    new = copy.deepcopy(config_dict)
    for param in _prepare_tunable_specs(tunable):
        if random.random() > rate:
            continue
        lo, hi = param["range"]
        obj = _resolve_parent(new, param["parents"])
        current = obj[param["leaf"]]
        delta = random.gauss(0, (hi - lo) * strength)
        obj[param["leaf"]] = _quantize(current + delta, lo, hi,
                                       param["integer"], param["step"])
    return new


def crossover(a, b, tunable):
    child = copy.deepcopy(a)
    for param in _prepare_tunable_specs(tunable):
        if random.random() < 0.5:
            obj_b = _resolve_parent(b, param["parents"])
            obj_c = _resolve_parent(child, param["parents"])
            obj_c[param["leaf"]] = obj_b[param["leaf"]]
    return child


def _worker(args):
    config_dict, fitness_def, safety_config, run_id = args
    cfg = DomainConfig.from_dict(config_dict)
    mc = run_monte_carlo(cfg, n_override=min(cfg.n_simulations, 2000))
    safety = evaluate_safety(mc, safety_config) if safety_config else {"all_passed": True}
    fitness = compute_fitness(mc, fitness_def, safety_config, safety_result=safety)
    
    return {
        "id": run_id, "fitness": fitness, "config": config_dict,
        "stats": mc["stats"], "safety": safety,
    }


def evolve(domain_path_or_dict, generations=15, population=20,
           workers=1, verbose=True):
    if isinstance(domain_path_or_dict, str):
        with open(domain_path_or_dict) as f:
            base_dict = json.load(f)
    else:
        base_dict = domain_path_or_dict
    
    config = DomainConfig.from_dict(base_dict)
    tunable = config.tunable
    fitness_def = config.fitness
    safety_config = config.safety or None

    if not (fitness_def and fitness_def.get("components")):
        raise ValueError(
            f"Cannot optimize '{config.name}': no 'fitness' objective defined. "
            "Add a fitness block, e.g. "
            '{"components": [{"expr": "<metric>_median", "weight": 1.0}]}, '
            "so the optimizer knows what to maximize."
        )
    if not tunable:
        raise ValueError(
            f"Cannot optimize '{config.name}': no 'tunable' levers defined. "
            "Add a tunable list of {\"path\": ..., \"range\": [lo, hi]} entries."
        )
    
    manifest = make_manifest(base_dict, config.n_simulations, config.seed,
                             {"generations": generations, "population": population})
    
    if verbose:
        print(f"SimEngine v3 Evolve: {config.name}")
        print(f"Generations: {generations} | Population: {population} | Workers: {workers}")
        print(f"Safety constraints: {len(safety_config.get('chance_constraints', [])) + len(safety_config.get('cvar_constraints', []))} active" if safety_config else "Safety: unconstrained")
        print(f"Manifest: {manifest['config_hash']}")
        print("=" * 70)
    
    # Initialize population. Quantize the seed's tunable values so an off-grid
    # author value (e.g. an integer control seeded at 2.5) never survives as the
    # reported best when the unmutated base wins.
    pop = [copy.deepcopy(base_dict)]
    for spec in _prepare_tunable_specs(tunable):
        try:
            parent = _resolve_parent(pop[0], spec["parents"])
            lo, hi = spec["range"]
            parent[spec["leaf"]] = _quantize(parent[spec["leaf"]], lo, hi,
                                             spec["integer"], spec["step"])
        except (KeyError, TypeError):
            pass
    for _ in range(population - 1):
        pop.append(mutate_config(base_dict, tunable, rate=0.8, strength=0.25))
    
    best_ever = None
    history = []
    
    for gen in range(generations):
        t0 = time.time()
        
        items = [(cfg, fitness_def, safety_config, f"g{gen}_i{i}") for i, cfg in enumerate(pop)]
        
        scored = []
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futs = [pool.submit(_worker, item) for item in items]
                for f in as_completed(futs):
                    scored.append(f.result())
        else:
            for item in items:
                scored.append(_worker(item))
        
        scored.sort(key=lambda x: x["fitness"], reverse=True)
        best = scored[0]
        
        if best_ever is None or best["fitness"] > best_ever["fitness"]:
            best_ever = copy.deepcopy(best)
        
        fits = [s["fitness"] for s in scored]
        safe_count = sum(1 for s in scored if s["safety"]["all_passed"])
        elapsed = time.time() - t0
        
        top_metric = list(best["stats"].keys())[0]
        top_val = best["stats"][top_metric]["median"]
        
        history.append({
            "gen": gen, "best_fit": best["fitness"],
            "avg_fit": round(sum(fits)/len(fits), 2),
            "safe_pct": round(safe_count/len(scored)*100, 1),
            "elapsed": round(elapsed, 1),
        })
        
        if verbose:
            safe_tag = f"safe:{safe_count}/{len(scored)}" if safety_config else ""
            print(f"Gen {gen:>3d} | fit:{best['fitness']:>6.1f} | "
                  f"avg:{history[-1]['avg_fit']:>6.1f} | "
                  f"{top_metric}:{top_val:>10,.0f} | "
                  f"{safe_tag} | {elapsed:.1f}s")
        
        if gen < generations - 1:
            next_gen = [scored[i]["config"] for i in range(min(2, len(scored)))]
            while len(next_gen) < population:
                parents = random.sample(scored[:max(3, len(scored)//2)], 2)
                child = crossover(parents[0]["config"], parents[1]["config"], tunable)
                child = mutate_config(child, tunable, rate=0.25, strength=0.1)
                next_gen.append(child)
            pop = next_gen[:population]
    
    if verbose:
        print("=" * 70)
        print(f"Best fitness: {best_ever['fitness']}")
        if best_ever.get("safety"):
            safe = best_ever["safety"]
            print(f"Safety: {'ALL PASSED' if safe['all_passed'] else 'VIOLATIONS DETECTED'}")
            for c in safe.get("chance", []):
                status = "PASS" if c["passed"] else "FAIL"
                print(f"  [{status}] P({c['metric']} {c['condition']} {c['threshold']:,}) = {c['actual_prob']:.1%} (max {c['max_prob']:.1%})")
            for c in safe.get("cvar", []):
                status = "PASS" if c["passed"] else "FAIL"
                print(f"  [{status}] CVaR_{c['alpha']} of {c['metric']} = {c['actual_cvar']:,.0f} (min {c['min_cvar']:,})")
    
    # Surface the winning lever values so the optimum is actionable. They live
    # in best_ever["config"] at the tunable paths; project them out by path.
    best_controls = {}
    if best_ever is not None:
        for spec in _prepare_tunable_specs(tunable):
            try:
                parent = _resolve_parent(best_ever["config"], spec["parents"])
                best_controls[spec["path"]] = parent[spec["leaf"]]
            except (KeyError, TypeError):
                pass

    return {
        "best": best_ever, "best_controls": best_controls, "history": history,
        "manifest": manifest, "domain": config.name,
    }


# ---------------------------------------------------------------------------
# Pretty Print
# ---------------------------------------------------------------------------
def print_results(r):
    print("=" * 60)
    print(f"SIMULATION: {r['domain']} | N={r['n_simulations']:,}")
    print("=" * 60)
    for mname, s in r["stats"].items():
        fmt = s.get("format", "number")
        print(f"\n--- {mname} ---")
        if fmt == "dollar":
            print(f"  Mean:   ${s['mean']:>12,.0f}  |  Median: ${s['median']:>12,.0f}")
            print(f"  P10:    ${s['p10']:>12,.0f}  |  P90:    ${s['p90']:>12,.0f}")
        elif fmt == "percent":
            print(f"  Mean:   {s['mean']:>8.1%}  |  Median: {s['median']:>8.1%}")
            print(f"  P10:    {s['p10']:>8.1%}  |  P90:    {s['p90']:>8.1%}")
        else:
            print(f"  Mean:   {s['mean']:>12.2f}  |  Median: {s['median']:>12.2f}")
            print(f"  P10:    {s['p10']:>12.2f}  |  P90:    {s['p90']:>12.2f}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    p = argparse.ArgumentParser(description="SimEngine v3")
    p.add_argument("domain")
    p.add_argument("--evolve", action="store_true")
    p.add_argument("--generations", "-g", type=int, default=15)
    p.add_argument("--population", "-p", type=int, default=20)
    p.add_argument("--workers", "-w", type=int, default=1)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--output", "-o", type=str, default=None)
    args = p.parse_args()
    
    if args.evolve:
        result = evolve(args.domain, args.generations, args.population, args.workers)
        out = args.output or "evolution_results.json"
        with open(out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved to {out}")
    else:
        cfg = DomainConfig.from_json(args.domain)
        mc = run_monte_carlo(cfg, seed=args.seed)
        print_results(mc)
        
        if cfg.safety:
            safety = evaluate_safety(mc, cfg.safety)
            print("\nSafety Evaluation:")
            for c in safety.get("chance", []):
                s = "PASS" if c["passed"] else "FAIL"
                print(f"  [{s}] P({c['metric']} {c['condition']} {c['threshold']:,}) = {c['actual_prob']:.1%} <= {c['max_prob']:.1%}")
            for c in safety.get("cvar", []):
                s = "PASS" if c["passed"] else "FAIL"
                print(f"  [{s}] CVaR_{c['alpha']} {c['metric']} = {c['actual_cvar']:,.0f} >= {c['min_cvar']:,}")
        
        out = args.output or "sim_results.json"
        with open(out, "w") as f:
            json.dump(mc, f, indent=2, default=str)
        print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()

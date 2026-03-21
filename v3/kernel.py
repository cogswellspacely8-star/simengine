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

import json, random, math, copy, time, statistics, sys, hashlib
from dataclasses import dataclass, field
from typing import Any, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

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
    return sum(1 for _ in range(int(round(n))) if random.random() < p)

def _clamp(v, lo, hi): return max(lo, min(hi, v))

SAFE_BUILTINS = {
    "min": min, "max": max, "abs": abs, "round": round,
    "sum": sum, "len": len, "int": int, "float": float,
    "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
    "ceil": math.ceil, "floor": math.floor, "pow": pow,
    "random": random.random, "gauss": random.gauss,
    "binomial": _binomial, "clamp": _clamp,
    "range": range, "True": True, "False": False,
}

def eval_expr(expr, state):
    try:
        return eval(expr, {"__builtins__": SAFE_BUILTINS}, state)
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
def simulate_one(config):
    state = dict(config.initial_state)
    state["_step"] = 0
    for acc in config.accumulators:
        if acc not in state:
            state[acc] = 0.0
    
    history = []
    for step in range(1, config.n_steps + 1):
        state["_step"] = step
        step_rec = {"_step": step}
        
        for vname, vdef in config.all_variables.items():
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


def run_monte_carlo(config, seed=None, n_override=None):
    n = n_override or config.n_simulations
    if seed is not None:
        random.seed(seed)
    
    all_metrics = {m: [] for m in config.metrics}
    all_histories = []
    
    for _ in range(n):
        r = simulate_one(config)
        for m, v in r["metrics"].items():
            all_metrics[m].append(v)
        all_histories.append(r["history"])
    
    stats = {}
    for mname, vals in all_metrics.items():
        sv = sorted(vals)
        fmt = config.metrics[mname].get("format", "number")
        stats[mname] = {
            "mean": round(statistics.mean(vals), 2),
            "median": round(statistics.median(vals), 2),
            "std": round(statistics.stdev(vals), 2) if len(vals) > 1 else 0,
            "p10": round(percentile(sv, 10), 2),
            "p25": round(percentile(sv, 25), 2),
            "p75": round(percentile(sv, 75), 2),
            "p90": round(percentile(sv, 90), 2),
            "format": fmt,
        }
    
    # Trajectory percentiles
    trajectories = {}
    for acc in config.accumulators:
        p10, p50, p90 = [], [], []
        for si in range(config.n_steps):
            vals = sorted([h[si].get(acc, 0) for h in all_histories])
            p10.append(round(percentile(vals, 10), 2))
            p50.append(round(percentile(vals, 50), 2))
            p90.append(round(percentile(vals, 90), 2))
        trajectories[acc] = {"p10": p10, "p50": p50, "p90": p90}
    
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
    results = {"chance": [], "cvar": [], "all_passed": True}
    raw = mc_result.get("raw_metrics", {})
    
    for cc in safety_config.get("chance_constraints", []):
        metric = cc["metric"]
        vals = raw.get(metric, [])
        if not vals:
            continue
        
        threshold = cc["threshold"]
        max_prob = cc["max_prob"]
        
        if cc["condition"] == "below":
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

# ---------------------------------------------------------------------------
# Fitness with Safety Penalty
# ---------------------------------------------------------------------------
def compute_fitness(mc_result, fitness_def, safety_config=None):
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
        safety = evaluate_safety(mc_result, safety_config)
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

def mutate_config(config_dict, tunable, rate=0.3, strength=0.15):
    new = copy.deepcopy(config_dict)
    for param in tunable:
        if random.random() > rate:
            continue
        path = param["path"]
        lo, hi = param["range"]
        parts = path.split(".")
        obj = new
        for p in parts[:-1]:
            obj = obj[p]
        current = obj[parts[-1]]
        delta = random.gauss(0, (hi - lo) * strength)
        obj[parts[-1]] = round(max(lo, min(hi, current + delta)), 4)
    return new


def crossover(a, b, tunable):
    child = copy.deepcopy(a)
    for param in tunable:
        if random.random() < 0.5:
            path = param["path"]
            parts = path.split(".")
            obj_b = b
            for p in parts[:-1]:
                obj_b = obj_b[p]
            obj_c = child
            for p in parts[:-1]:
                obj_c = obj_c[p]
            obj_c[parts[-1]] = obj_b[parts[-1]]
    return child


def _worker(args):
    config_dict, fitness_def, safety_config, run_id = args
    cfg = DomainConfig.from_dict(config_dict)
    mc = run_monte_carlo(cfg, n_override=min(cfg.n_simulations, 2000))
    fitness = compute_fitness(mc, fitness_def, safety_config)
    safety = evaluate_safety(mc, safety_config) if safety_config else {"all_passed": True}
    
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
    
    manifest = make_manifest(base_dict, config.n_simulations, config.seed,
                             {"generations": generations, "population": population})
    
    if verbose:
        print(f"SimEngine v3 Evolve: {config.name}")
        print(f"Generations: {generations} | Population: {population} | Workers: {workers}")
        print(f"Safety constraints: {len(safety_config.get('chance_constraints', [])) + len(safety_config.get('cvar_constraints', []))} active" if safety_config else "Safety: unconstrained")
        print(f"Manifest: {manifest['config_hash']}")
        print("=" * 70)
    
    # Initialize population
    pop = [copy.deepcopy(base_dict)]
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
    
    return {
        "best": best_ever, "history": history,
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

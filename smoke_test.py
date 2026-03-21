#!/usr/bin/env python3
"""
SimEngine Smoke Test
=====================
Run this after copying to your system to verify everything works.

Usage:
    cd simengine/v3
    python ../smoke_test.py
"""

import sys, os, time

# Add v3 to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'v3'))

PASS = 0
FAIL = 0

def test(name, fn):
    global PASS, FAIL
    try:
        result = fn()
        if result:
            print(f"  [PASS] {name}")
            PASS += 1
        else:
            print(f"  [FAIL] {name} (returned False)")
            FAIL += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        FAIL += 1


print("=" * 60)
print("SimEngine Smoke Test")
print("=" * 60)

# --- Test 1: v3 kernel imports ---
print("\n1. Kernel imports")
def t_import():
    from kernel import DomainConfig, run_monte_carlo, evolve, evaluate_safety, compute_cvar
    return True
test("v3 kernel imports", t_import)

# --- Test 2: Load domain config ---
print("\n2. Domain config loading")
def t_load():
    from kernel import DomainConfig
    cfg = DomainConfig.from_json("domains/business_pipeline_v3.json")
    assert cfg.name == "Venture Horizon Pipeline v3 (Calibrated)"
    assert len(cfg.parameters) > 0
    assert len(cfg.controls) > 0
    assert len(cfg.exogenous) > 0
    assert cfg.safety is not None
    return True
test("Load business_pipeline_v3.json", t_load)

def t_load_job():
    from kernel import DomainConfig
    cfg = DomainConfig.from_json("domains/job_search.json")
    assert cfg.n_steps == 26
    return True
test("Load job_search.json", t_load_job)

def t_load_inv():
    from kernel import DomainConfig
    cfg = DomainConfig.from_json("domains/investment_portfolio_v2.json")
    assert cfg.n_steps == 120
    return True
test("Load investment_portfolio_v2.json", t_load_inv)

# --- Test 3: Monte Carlo run ---
print("\n3. Monte Carlo simulation")
def t_mc():
    from kernel import DomainConfig, run_monte_carlo
    cfg = DomainConfig.from_json("domains/business_pipeline_v3.json")
    t0 = time.time()
    mc = run_monte_carlo(cfg, seed=42, n_override=500)
    elapsed = time.time() - t0
    assert "annual_revenue" in mc["stats"]
    assert mc["stats"]["annual_revenue"]["mean"] > 0
    assert mc["n_simulations"] == 500
    print(f"          500 runs in {elapsed:.1f}s | Revenue mean: ${mc['stats']['annual_revenue']['mean']:,.0f}")
    return True
test("Business pipeline MC (N=500)", t_mc)

# --- Test 4: Safety evaluation ---
print("\n4. Safety constraints")
def t_safety():
    from kernel import DomainConfig, run_monte_carlo, evaluate_safety
    cfg = DomainConfig.from_json("domains/business_pipeline_v3.json")
    mc = run_monte_carlo(cfg, seed=42, n_override=1000)
    safety = evaluate_safety(mc, cfg.safety)
    assert "chance" in safety
    assert "cvar" in safety
    assert len(safety["chance"]) > 0
    assert len(safety["cvar"]) > 0
    cc = safety["chance"][0]
    cv = safety["cvar"][0]
    print(f"          P(ruin) = {cc['actual_prob']:.1%} (limit {cc['max_prob']:.1%}) [{'PASS' if cc['passed'] else 'FAIL'}]")
    print(f"          CVaR(10%) = ${cv['actual_cvar']:,.0f} (limit ${cv['min_cvar']:,}) [{'PASS' if cv['passed'] else 'FAIL'}]")
    return True
test("Chance + CVaR constraints", t_safety)

# --- Test 5: Experiment manifest ---
print("\n5. Reproducibility")
def t_manifest():
    from kernel import make_manifest
    m = make_manifest({"test": True}, 5000, 42)
    assert "config_hash" in m
    assert m["kernel_version"] == "3.0.0"
    assert m["seed"] == 42
    print(f"          Manifest hash: {m['config_hash']}")
    return True
test("Experiment manifest generation", t_manifest)

# --- Test 6: Diagnostics (if available) ---
print("\n6. Diagnostics")
def t_diag_convergence():
    from diagnostics import convergence_analysis
    from kernel import DomainConfig
    cfg = DomainConfig.from_json("domains/business_pipeline_v3.json")
    result = convergence_analysis(cfg, checkpoints=[100, 500, 1000], metric="annual_revenue", max_runs=1000)
    assert result["convergence_n"] is not None or len(result["checkpoints"]) > 0
    last = result["checkpoints"][-1]
    print(f"          N=1000: mean=${last['mean']:,.0f}, CI95={last['ci95_pct']:.1f}%")
    return True
test("Convergence analysis", t_diag_convergence)

def t_diag_baseline():
    from diagnostics import compare_to_baseline
    from kernel import DomainConfig
    cfg = DomainConfig.from_json("domains/business_pipeline_v3.json")
    result = compare_to_baseline(cfg, n_simulations=500)
    c = result["comparison"]["annual_revenue"]
    print(f"          Deterministic: ${c['deterministic']:,.0f} vs MC mean: ${c['mc_mean']:,.0f}")
    return True
test("Baseline comparison", t_diag_baseline)

# --- Test 7: Student's t distribution ---
print("\n7. Fat-tail distributions")
def t_student():
    import diagnostics  # registers student_t sampler
    from kernel import DomainConfig, run_monte_carlo
    cfg = DomainConfig.from_json("domains/investment_portfolio_v2.json")
    mc = run_monte_carlo(cfg, seed=42, n_override=500)
    dd = mc["stats"]["max_drawdown"]["median"]
    print(f"          Student-t investment model: median max drawdown = {dd:.0%}")
    assert dd > 0
    return True
test("Student-t investment model", t_student)

# --- Test 8: Cross-domain generalization ---
print("\n8. Cross-domain (same kernel, different problems)")
def t_cross():
    from kernel import DomainConfig, run_monte_carlo
    domains = [
        ("domains/business_pipeline_v3.json", "annual_revenue"),
        ("domains/job_search.json", "best_salary_offer"),
        ("domains/investment_portfolio.json", "final_value"),
    ]
    for path, metric in domains:
        cfg = DomainConfig.from_json(path)
        mc = run_monte_carlo(cfg, seed=42, n_override=200)
        val = mc["stats"][metric]["median"]
        fmt = mc["stats"][metric].get("format", "number")
        if fmt == "dollar":
            print(f"          {cfg.name}: {metric} = ${val:,.0f}")
        else:
            print(f"          {cfg.name}: {metric} = {val:,.1f}")
    return True
test("Three domains on one kernel", t_cross)

# --- Summary ---
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"Results: {PASS}/{total} passed, {FAIL}/{total} failed")
if FAIL == 0:
    print("All systems operational. SimEngine is ready.")
else:
    print(f"WARNING: {FAIL} test(s) failed. Check output above.")
print("=" * 60)

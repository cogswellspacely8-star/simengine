# SimEngine — Local-First Simulation & Decision Intelligence

A domain-agnostic Monte Carlo simulation kernel with safety-constrained
evolutionary optimization, built for personal and small-business decision
support on commodity hardware.

**Zero dependencies. Pure Python stdlib. Runs anywhere.**

---

## Quick start (your system)

```bash
# 1. Clone or copy this directory to your main-pc
#    Recommended location: ~/projects/simengine/
cp -r simengine-release ~/projects/simengine
cd ~/projects/simengine

# 2. Run a simulation (v3 is the current production version)
cd v3
python -m kernel domains/business_pipeline_v3.json

# 3. Run with evolutionary optimization
python -m kernel domains/business_pipeline_v3.json --evolve -g 15 -p 20 -w 8

# 4. Run diagnostics (convergence, sensitivity, baseline comparison)
python -m diagnostics domains/business_pipeline_v3.json --convergence
python -m diagnostics domains/business_pipeline_v3.json --sensitivity
python -m diagnostics domains/business_pipeline_v3.json --baseline

# 5. Try a different domain (same kernel, no code changes)
python -m kernel domains/job_search.json
python -m kernel domains/investment_portfolio_v2.json
```

## Hardware deployment map

```
main-pc (your primary workstation)
├── Heavy simulation runs (5,000-20,000 MC)
├── Evolutionary optimization (use --workers 8 for all cores)
├── Diagnostics suite
└── Results analysis

rosie / orin (edge node)
├── Lightweight simulation runs (1,000 MC)
├── Scheduled domain checks (cron)
├── JSON results back to main-pc
└── Eventually: agent-based model runs

Aether Console (https://10.88.88.101:8082)
├── Future: dispatch simulation jobs via task queue
├── Future: display results in dashboard
└── Future: trigger from Missions or Agents tab
```

## Directory structure

```
simengine/
├── v1/                          # Original hardcoded engine
│   ├── core.py                  # Business pipeline Monte Carlo
│   ├── swarm.py                 # Evolutionary optimizer (business-specific)
│   └── venture_horizon_config.json
│
├── v2/                          # Universal kernel (domain-agnostic)
│   ├── kernel.py                # Domain-agnostic MC engine
│   ├── diagnostics.py           # Convergence, sensitivity, baseline, security
│   └── domains/
│       ├── business_pipeline.json
│       ├── job_search.json
│       ├── investment_portfolio.json
│       └── investment_portfolio_v2.json  # Fat-tailed returns
│
├── v3/                          # CURRENT — restructured + safety constraints
│   ├── kernel.py                # v3 kernel: typed schema, CVaR, manifests
│   ├── diagnostics.py           # Same diagnostics, compatible with v3
│   ├── __init__.py
│   └── domains/
│       ├── business_pipeline_v3.json   # Calibrated, safety-constrained
│       ├── job_search.json
│       ├── investment_portfolio.json
│       ├── investment_portfolio_v2.json
│       └── _template.json              # Copy this to create new domains
│
└── docs/
    └── System_Report_v2_SimEngine.docx  # The paper
```

## Version differences

| Feature | v1 | v2 | v3 |
|---------|----|----|-----|
| Domain logic | Hardcoded Python | JSON config | JSON config (typed) |
| Schema | Python classes | Flat "variables" | parameters/controls/exogenous |
| Optimizer | GA, no safety | GA, weighted fitness | GA + CVaR + chance constraints |
| Diagnostics | None | Convergence + sensitivity | + baseline comparison |
| Calibration | None | None | Per-variable metadata |
| Reproducibility | None | None | SHA-256 manifest per run |
| Security | N/A | eval() sandbox | eval() + AST evaluator |

**Use v3 for everything new.** v1 and v2 are preserved for reference.

## Creating a new domain

```bash
cd v3
cp domains/_template.json domains/my_problem.json
# Edit my_problem.json with your variables, logic, metrics, and safety constraints
python -m kernel domains/my_problem.json
```

### Domain config anatomy (v3 schema)

```
{
  "parameters": {    # Uncertain — updated by evidence
    "close_rate": { "distribution": "triangular", "params": {...}, "calibration": {...} }
  },
  "controls": {      # Your decisions
    "pricing": { "distribution": "fixed", "params": {"value": 5000} }
  },
  "exogenous": {     # External shocks you can't control
    "leads": { "distribution": "triangular", "params": {...} }
  },
  "step_logic": [...],     # What happens each timestep
  "accumulators": {...},   # Running totals
  "metrics": {...},        # What to measure
  "safety": {              # Constraints the optimizer must respect
    "chance_constraints": [...],
    "cvar_constraints": [...]
  },
  "fitness": {...},        # What "good" means (for optimizer)
  "tunable": [...]         # What the optimizer can adjust
}
```

### Available distributions

| Type | Params | When to use |
|------|--------|-------------|
| `fixed` | `value` | Known constants |
| `uniform` | `low, high` | Equal probability across range |
| `triangular` | `low, mode, high` | Expert estimates (min/likely/max) |
| `normal` | `mean, std, min?, max?` | Bell curve (clamped) |
| `lognormal` | `median, spread, min?, max?` | Always positive, right-skewed (prices, durations) |
| `bernoulli` | `p` | Yes/no events |
| `poisson` | `lambda` | Count of rare events |
| `student_t` | `mean, scale, df, min?, max?` | Fat-tailed returns (use df=5 for equities) |

### Expression helpers

Use these in `step_logic`, `accumulators`, and `metrics`:

- `binomial(n, p)` — N trials with probability P, returns # successes
- `clamp(val, lo, hi)` — bound a value
- `random()` — uniform 0-1
- `min, max, abs, round, sqrt, log, exp, pow`

## Running on Rosie/Orin

The kernel is a single Python file with zero dependencies. Copy it directly:

```bash
# From main-pc
scp -r v3/ rosie:~/simengine/

# On Rosie — run a lighter simulation
ssh rosie
cd ~/simengine
python -m kernel domains/business_pipeline_v3.json --seed 42

# Or run on a schedule (cron)
# 0 6 * * 1 cd ~/simengine && python -m kernel domains/business_pipeline_v3.json -o /tmp/weekly_sim.json
```

Results are JSON — pipe them anywhere: Aether Console, a web dashboard, a Slack webhook, or just read the file.

## Integration with Aether Console (future)

The JSON-in/JSON-out interface means SimEngine can plug into your existing
infrastructure through any of these paths:

```
1. Task queue:  Aether dispatches a simulation config → kernel runs → results back
2. HTTP wrapper: Flask/FastAPI around kernel.py (add 20 lines)
3. Agent call:  An agent in the Agents tab triggers a simulation
4. CLI cron:    Scheduled runs that push results to the dashboard
5. LLM tool:   Claude Code or local LLM generates a domain config → kernel runs it
```

None of these require changes to the kernel. The integration layer is thin
because the interface is already clean.

## CLI reference

### kernel.py

```bash
# Run Monte Carlo
python -m kernel <domain.json> [--seed N] [--output results.json]

# Run evolutionary optimization
python -m kernel <domain.json> --evolve [-g generations] [-p population] [-w workers] [-o output.json]
```

### diagnostics.py

```bash
# Convergence analysis (proves sample size is sufficient)
python -m diagnostics <domain.json> --convergence [--metric annual_revenue]

# Sensitivity analysis (which inputs matter most)
python -m diagnostics <domain.json> --sensitivity [--metric annual_revenue]

# Baseline comparison (Monte Carlo vs spreadsheet)
python -m diagnostics <domain.json> --baseline
```

## What the numbers mean

When you run a simulation, you get:

- **Mean**: average across all simulated futures
- **Median**: the 50th percentile (half of futures are above, half below)
- **P10**: pessimistic — only 10% of futures are worse than this
- **P90**: optimistic — only 10% of futures are better than this
- **CVaR(10%)**: the average outcome in the worst 10% of futures

Safety constraints tell you:
- **Chance constraint**: "the probability of [bad thing] must stay below X%"
- **CVaR constraint**: "even in the worst scenarios, the loss must not exceed $Y"

If the optimizer finds a strategy where these constraints are violated, it
penalizes that strategy and steers toward safer configurations.

## License and status

This is a working prototype under active development by Venture Horizon LLC.
Not yet released as open source. The System Report (docs/) documents the
methodology, evidence, and limitations.

Current status: v3 kernel operational, safety constraints working, diagnostics
complete. Next priorities: AST evaluator migration, conjugate Bayesian updates,
historical data calibration.

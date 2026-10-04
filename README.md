# SimEngine

**A domain-agnostic Monte Carlo simulation and decision intelligence system.**

Zero dependencies. Pure Python stdlib. Local web UI. Runs anywhere Python runs.

SimEngine turns uncertainty into numbers you can act on. Define your variables, your logic, and your risk tolerances in a JSON config. The engine runs thousands of simulated futures, scores them, and — if you ask — evolves toward the best strategy that still respects your safety constraints.

Think of it as a calculator for uncertainty.

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> ~/projects/simengine
cd ~/projects/simengine

# 2. Start the web UI
cd v3 && python3 server.py

# 3. Open your browser
#    http://localhost:8420
```

That is it. No `pip install`, no Docker, no Node, no build step. Python 3.8+ is the only requirement.

## Install as an MCP server

    uvx simengine-mcp

Listed on the [official MCP registry](https://registry.modelcontextprotocol.io/?search=simengine).
Hosted, no-install endpoint: [join the waitlist](https://cogswellspacely8-star.github.io/simengine-site/#waitlist).

## Optional Native Acceleration

The default engine remains pure Python. A Rust workspace now lives at the repo root
for optional acceleration of metric reducers, trajectory bands, risk evaluation,
histograms, and native pre-sampling of simple numeric variable distributions.

This is opt-in and does not change the baseline workflow above.

### Workspace layout

```text
Cargo.toml
crates/
├── simengine-core/   # pure Rust numeric kernels
└── simengine-py/     # PyO3 extension module: simengine_native
v3/native.py          # optional loader + Python fallback glue
```

### Build the native extension

```bash
cd crates/simengine-py
python3 -m venv ../../.venv
source ../../.venv/bin/activate
pip install maturin
maturin develop --release
```

After that, the existing Python engine will automatically use the native
reducers and the native batch sampler when `simengine_native` is importable.
If the module is missing or fails, SimEngine falls back to the existing
Python implementation.

The batch sampler is conservative:
- it only activates for plain numeric variable params
- it stays off for correlated configs
- it can be disabled explicitly with `SIMENGINE_DISABLE_NATIVE_SAMPLING=1`

This keeps the expression engine, accumulators, and metrics in Python while
moving a larger chunk of the Monte Carlo loop into Rust.

There is also a narrower native fast path for stochastic expressions:
- `binomial(n, p)` can be delegated to Rust when the extension is installed
- it can be disabled explicitly with `SIMENGINE_DISABLE_NATIVE_EXPR_SAMPLING=1`

This helps domains whose `step_logic` relies heavily on `binomial(...)` while
still leaving general expression evaluation in Python.

On the Python side, repeated expressions are now compiled once and reused
across Monte Carlo runs. That cache can be disabled explicitly with
`SIMENGINE_DISABLE_EXPR_CACHE=1` for benchmarking or troubleshooting.

The diagnostics module applies the same idea to its AST-only safe evaluator:
parsed trees are reused across calls, and that cache can be disabled with
`SIMENGINE_DISABLE_SAFE_EXPR_CACHE=1`.

---

## What It Does

- **Monte Carlo simulation** -- Run 5,000+ parallel futures for any domain you can describe in JSON.
- **Safety constraints** -- Chance constraints ("at most 15% probability of going broke") and CVaR constraints ("the average worst-case loss must not exceed $X").
- **Genetic optimizer** -- Evolve control parameters toward the best outcome while respecting safety bounds. Crossover, mutation, elitism, tournament selection.
- **Bayesian updating** -- Feed observed data back into your model. Conjugate priors (Beta-Binomial, Gamma-Poisson, Normal-Normal) tighten distributions as evidence arrives.
- **Diagnostics** -- Convergence analysis (proves your sample size is sufficient), sensitivity analysis (ranks which inputs drive the output), deterministic baseline comparison (quantifies the value of simulation over spreadsheet math).
- **Web UI** -- Histograms, trajectory fans, risk gauges, scenario comparison with control sweeps and input diffs, domain wizard, Bayesian update modal, export to standalone HTML report.
- **AI agent integration** -- POST a config inline to `/api/simulate` and get structured results back. No files needed. LLMs can use SimEngine as a tool (`llms.txt` at the repo root and `GET /llms.txt` orient them).
- **Validated calibration** -- A sqlite forecast ledger scores predictions with proper scoring rules (Brier / log-loss / CRPS), and the pipeline is backtested on ~2,800 walk-forward monthly forecasts over decades of public FRED data. Run it yourself: `cd v3 && python3 backtest.py` (offline, from committed snapshots). Results: [docs/backtests/](docs/backtests/2026-07-06-fred-monthly-calibration.md).

---

## Architecture

All production code lives in `v3/`.

```
v3/
├── kernel.py          Monte Carlo engine, distributions, safety evaluation,
│                      fitness scoring, genetic optimizer, experiment manifests
├── server.py          HTTP server (port 8420), all API endpoints, report generation
├── bayesian.py        Conjugate prior updates for calibrating parameters from data
├── diagnostics.py     Convergence, sensitivity (OAT), baseline comparison, AST evaluator
├── static/
│   └── index.html     Single-page web UI (vanilla HTML/JS/CSS, no framework)
└── domains/
    ├── _template.json              Annotated starter config
    ├── business_pipeline_v3.json   B2B sales pipeline
    ├── investment_portfolio.json   Portfolio allocation
    ├── investment_portfolio_v2.json  Fat-tailed returns (Student's t)
    ├── job_search.json             Job search decision model
    ├── project_timeline.json       Software project estimation
    ├── real_estate_rental.json     Rental property analysis
    └── saas_startup.json           SaaS MRR growth and runway
```

---

## Domain Config Schema

A domain config is a single JSON file that fully describes the simulation. The v3 schema separates variables into three semantic categories, which matters for Bayesian updating and optimization.

**Published contract:** the machine-readable [JSON Schema](v3/schema/domain.schema.json) (Draft 2020-12) is served live at `GET /api/schema` — hand it to any AI to author a valid config in one shot. A plain-language field reference is in [`docs/schema-reference.md`](docs/schema-reference.md). The schema is verified against every shipped domain in the test suite.

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable domain name |
| `description` | string | What this simulation models |
| `n_simulations` | int | Number of Monte Carlo runs (default: 5000) |
| `n_steps` | int | Time steps per simulation (e.g., 12 months) |
| `step_label` | string | Label for time axis: "month", "week", "sprint" |
| `seed` | int or null | Random seed for reproducibility |
| `parameters` | object | Uncertain variables, updatable with evidence |
| `controls` | object | Operator decisions (pricing, budget, effort) |
| `exogenous` | object | External factors outside your control |
| `initial_state` | object | Starting values for accumulators |
| `step_logic` | array | Computations executed each time step |
| `accumulators` | object | Running totals updated each step |
| `metrics` | object | Final output measurements |
| `safety` | object | Chance constraints and CVaR constraints |
| `fitness` | object | Weighted scoring components for the optimizer |
| `tunable` | array | Parameters the optimizer is allowed to adjust |
| `context` | object | Optional metadata: decision question, key levers |
| `calibration` | object | Per-variable data source and update method |

### Variable Definition

All three variable categories (`parameters`, `controls`, `exogenous`) share the same structure:

```json
{
  "monthly_churn_rate": {
    "distribution": "triangular",
    "params": {"low": 0.02, "mode": 0.05, "high": 0.12},
    "calibration": {
      "source": "Baremetrics Open Benchmarks: median monthly churn 5-8%",
      "updatable": true,
      "update_method": "Beta-Binomial conjugate from observed monthly cancellations"
    }
  }
}
```

### Available Distributions

| Distribution | Params | Use Case |
|-------------|--------|----------|
| `fixed` | `value` | Known constants |
| `uniform` | `low`, `high` | Equal probability across a range |
| `triangular` | `low`, `mode`, `high` | Expert estimates (pessimistic / likely / optimistic) |
| `normal` | `mean`, `std`, `min?`, `max?` | Bell curve, optionally clamped |
| `lognormal` | `median`, `spread`, `min?`, `max?` | Always positive, right-skewed (prices, durations) |
| `bernoulli` | `p` | Binary yes/no events |
| `poisson` | `lambda` | Counts of rare events |
| `student_t` | `mean`, `scale`, `df`, `min?`, `max?` | Fat-tailed returns (use df=5 for equities) |
| `beta` | `alpha`, `beta`, `low?`, `high?` | Rates and probabilities; exact Beta-Binomial posteriors |
| `gamma` | `shape`, `scale` or `rate` | Positive rates and waiting times; exact Gamma-Poisson posteriors |
| `categorical` | `values`, `probs?` | Regimes and scenarios (recession / flat / boom) |
| `empirical` | `values`, `jitter?` | Bootstrap from observed data, no parametric assumption |

### Stochastic Processes

Processes are declared like distributions but carry their own value from step to
step, so autocorrelated quantities are first-class instead of hand-rolled in
`step_logic`. All parameters are per step; `z` is a standard-normal innovation
(correlate two processes' shocks through the `correlations` array like any other pair).

| Process | Params | Recursion |
|---------|--------|-----------|
| `random_walk` | `start`, `std`, `drift?`, `min?`, `max?` | `x = x_prev + drift + std*z` |
| `gbm` | `start`, `sigma`, `mu?`, `min?`, `max?` | `x = x_prev * exp(mu + sigma*z)` (mu = per-step log drift; mean grows at mu + sigma²/2) |
| `ar1` | `mean`, `phi`, `std`, `start?` | `x = mean + phi*(x_prev - mean) + std*z`, stationary for `\|phi\| < 1` |
| `mean_reverting` | `mean`, `theta`, `std`, `start?` | `x = x_prev + theta*(mean - x_prev) + std*z` (discrete Ornstein-Uhlenbeck; theta = fraction of the gap closed per step) |

See `domains/asset_price_paths.json` for two correlated GBM assets, a mean-reverting
rate, and a maximum-drawdown metric built from persistent `step_logic` targets.
| `correlated_normal` | `mean`, `std` | Normal with correlation support (via step_logic) |

### Step Logic

An ordered list of computations executed each time step. Each entry has a `target` name and either an `expr` (expression string) or a `sample` (inline distribution):

```json
"step_logic": [
  {"target": "new_leads",    "expr": "binomial(round(demand), conversion_rate)"},
  {"target": "revenue",      "expr": "new_leads * price_per_unit"},
  {"target": "costs",        "expr": "fixed_cost + variable_cost * new_leads"},
  {"target": "net_income",   "expr": "revenue - costs"},
  {"target": "shock_event",  "sample": {"distribution": "bernoulli", "params": {"p": 0.02}}}
]
```

**Available expression functions:** `min`, `max`, `abs`, `round`, `sum`, `len`, `int`, `float`, `sqrt`, `log`, `exp`, `ceil`, `floor`, `pow`, `random()`, `gauss(mu, sigma)`, `binomial(n, p)`, `clamp(val, lo, hi)`, `range()`. Ternary expressions work: `100 if x > 0 else 0`.

### Accumulators

Running state that persists across time steps:

```json
"accumulators": {
  "cumulative_revenue": "cumulative_revenue + revenue",
  "cash": "cash + net_income",
  "peak_subscribers": "max(peak_subscribers, subscribers)"
}
```

### Metrics

Final measurements computed after all steps complete:

```json
"metrics": {
  "total_revenue": {"expr": "cumulative_revenue",          "format": "dollar"},
  "roi":           {"expr": "cumulative_revenue / cumulative_costs", "format": "percent"},
  "final_subs":    {"expr": "subscribers",                 "format": "number"}
}
```

### Safety Constraints

```json
"safety": {
  "chance_constraints": [
    {
      "metric": "ending_cash",
      "condition": "below",
      "threshold": 0,
      "max_prob": 0.15,
      "rationale": "No more than 15% chance of running out of cash"
    }
  ],
  "cvar_constraints": [
    {
      "metric": "ending_cash",
      "alpha": 0.10,
      "min_cvar": -15000,
      "rationale": "Average of the worst 10% of outcomes must not exceed $15k loss"
    }
  ]
}
```

### Fitness and Tunable

The optimizer maximizes a weighted sum of fitness components while respecting safety constraints. Each component is an expression evaluated against the metric statistics (e.g., `total_revenue_median`, `ending_cash_p10`):

```json
"fitness": {
  "components": [
    {"expr": "min(100, final_mrr_median / 100)",  "weight": 0.30, "name": "mrr_growth"},
    {"expr": "max(0, 100 - months_negative_median * 5)", "weight": 0.25, "name": "time_to_profit"}
  ]
},
"tunable": [
  {"path": "controls.price_per_seat.params.value",      "range": [9, 99]},
  {"path": "parameters.monthly_churn_rate.params.mode",  "range": [0.01, 0.10]}
]
```

Fitness expressions can reference any metric stat in the form `{metric_name}_{stat}` where stat is one of: `mean`, `median`, `std`, `p10`, `p25`, `p75`, `p90`.

Safety violations apply a 30% penalty per violated constraint. The optimizer learns to avoid them.

---

## API Reference

The server runs at `http://localhost:8420`. All POST endpoints accept and return JSON. CORS headers are included on all responses.

### GET /api/domains

List all available domain configs.

**Response:**
```json
[
  {
    "file": "saas_startup.json",
    "name": "Indie SaaS -- MRR Growth & Runway",
    "description": "Models a bootstrapped SaaS product over 24 months...",
    "n_simulations": 5000,
    "n_steps": 24,
    "step_label": "month"
  }
]
```

### GET /api/domain/{filename}

Load a specific domain config by filename.

**Response:** The full JSON domain config object.

### POST /api/simulate

Run a Monte Carlo simulation.

**Request (file-based):**
```json
{
  "domain": "saas_startup.json",
  "n_simulations": 5000,
  "seed": 42,
  "overrides": {
    "controls.price_per_seat.params.value": 49
  }
}
```

**Request (inline config -- for AI agents):**
```json
{
  "config": { ... full domain config object ... },
  "n_simulations": 5000,
  "seed": 42
}
```

**Response:**
```json
{
  "domain": "Indie SaaS -- MRR Growth & Runway",
  "n_simulations": 5000,
  "elapsed": 1.23,
  "stats": {
    "final_mrr": {
      "mean": 4250.00,
      "median": 3915.00,
      "std": 2100.50,
      "p10": 1740.00,
      "p25": 2610.00,
      "p75": 5220.00,
      "p90": 7105.00,
      "format": "dollar"
    }
  },
  "trajectories": {
    "cash": {
      "p10": [24500, 23800, ...],
      "p50": [25100, 25300, ...],
      "p90": [25800, 26900, ...]
    }
  },
  "histograms": {
    "final_mrr": {
      "bins": [0.0, 250.0, ...],
      "counts": [12, 45, ...],
      "bin_width": 250.0,
      "lo": 0.0,
      "hi": 10000.0
    }
  },
  "safety": {
    "chance": [
      {"metric": "ending_cash", "condition": "below", "threshold": 0,
       "max_prob": 0.15, "actual_prob": 0.082, "passed": true}
    ],
    "cvar": [
      {"metric": "ending_cash", "alpha": 0.10, "min_cvar": -15000,
       "actual_cvar": -8500.00, "passed": true}
    ],
    "all_passed": true
  },
  "fitness": 72.5,
  "narrative": "**Final Mrr** is most likely $3,915 (range: $1,740 to $7,105 in 80% of scenarios)...",
  "context": {"decision": "Should I go full-time on this SaaS?"}
}
```

### POST /api/evolve

Run the genetic optimizer to find optimal control settings.

**Request:**
```json
{
  "domain": "saas_startup.json",
  "generations": 15,
  "population": 20
}
```

**Response:**
```json
{
  "domain": "Indie SaaS -- MRR Growth & Runway",
  "best_fitness": 85.3,
  "best_stats": { ... same format as simulate stats ... },
  "best_safety": { "all_passed": true, "chance": [...], "cvar": [...] },
  "history": [
    {"gen": 0, "best_fit": 62.1, "avg_fit": 45.3, "safe_pct": 60.0, "elapsed": 2.1},
    {"gen": 1, "best_fit": 68.5, "avg_fit": 52.1, "safe_pct": 75.0, "elapsed": 2.0}
  ],
  "elapsed": 31.5
}
```

### POST /api/validate

Validate a domain config without running a full simulation. Runs a 10-iteration test to catch expression errors.

**Request:**
```json
{
  "config": { ... domain config object ... }
}
```

**Response:**
```json
{
  "valid": true,
  "errors": []
}
```

Or on failure:
```json
{
  "valid": false,
  "errors": [
    "Variable 'close_rate': unknown distribution 'beta'",
    "step_logic[2]: missing 'target'"
  ]
}
```

### POST /api/save-domain

Validate and save a domain config to the `domains/` directory.

**Request:**
```json
{
  "config": { ... domain config object ... },
  "filename": "my_new_domain"
}
```

**Response:**
```json
{
  "saved": true,
  "file": "my_new_domain.json"
}
```

### POST /api/update

Bayesian update: feed observed data into a domain config and get updated parameter distributions plus a preview simulation.

**Request:**
```json
{
  "domain": "saas_startup.json",
  "observations": {
    "monthly_churn_rate": [0.04, 0.06, 0.03, 0.05],
    "organic_signup_rate": [18, 22, 15, 25, 20]
  }
}
```

**Response:**
```json
{
  "updated_config": { ... full config with tightened distributions ... },
  "update_report": {
    "monthly_churn_rate": {
      "method": "beta_binomial",
      "prior_mean": 0.05,
      "posterior_mean": 0.045,
      "posterior_std": 0.012,
      "observations_used": 4,
      "credible_interval_90": [0.025, 0.065]
    }
  },
  "preview_stats": { ... simulation results with updated params ... },
  "preview_safety": { ... }
}
```

### POST /api/report

Generate a standalone HTML report from simulation results.

**Request:**
```json
{
  "results": { ... simulate response object ... },
  "config": { ... domain config ... }
}
```

**Response:** HTML document (Content-Type: text/html). Self-contained, no external dependencies. Save it, email it, print it.

---

## CLI Usage

### kernel.py

```bash
cd ~/projects/simengine/v3

# Run a Monte Carlo simulation
python3 kernel.py domains/saas_startup.json

# Set a random seed for reproducibility
python3 kernel.py domains/saas_startup.json --seed 42

# Save results to a specific file
python3 kernel.py domains/saas_startup.json --output results.json

# Run evolutionary optimization
python3 kernel.py domains/saas_startup.json --evolve

# Customize optimizer parameters
python3 kernel.py domains/saas_startup.json --evolve \
  --generations 25 \
  --population 30 \
  --workers 8 \
  --output best_strategy.json
```

Short flags: `-g` (generations), `-p` (population), `-w` (workers), `-o` (output).

### diagnostics.py

```bash
cd ~/projects/simengine/v3

# Convergence analysis -- proves sample size is sufficient
# Runs at N=100, 250, 500, ..., 20000 and measures estimator stability.
python3 diagnostics.py domains/saas_startup.json --convergence

# Sensitivity analysis -- ranks which inputs drive the output
# One-at-a-time perturbation with normalized impact scores.
python3 diagnostics.py domains/saas_startup.json --sensitivity

# Baseline comparison -- Monte Carlo vs deterministic spreadsheet
# Shows the risk that point-estimate forecasting hides.
python3 diagnostics.py domains/saas_startup.json --baseline

# Target a specific metric (default: first metric defined)
python3 diagnostics.py domains/saas_startup.json --convergence --metric ending_cash

# Save results to JSON
python3 diagnostics.py domains/saas_startup.json --convergence --output conv.json
```

You can combine flags: `--convergence --sensitivity --baseline` runs all three.

---

## Creating a New Domain

There are three ways to create a domain config.

### 1. Web UI Wizard

Open `http://localhost:8420`, click the domain wizard, and fill in the form. The wizard generates a valid config, validates it, and saves it to the `domains/` directory.

### 2. Copy the Template

```bash
cp ~/projects/simengine/v3/domains/_template.json ~/projects/simengine/v3/domains/my_problem.json
```

Edit `my_problem.json`. The template includes inline documentation in the `_guide` field and a working example structure. Replace the placeholder variables, logic, and metrics with your own.

### 3. Generate with an LLM

Describe your problem to an LLM and ask it to produce a SimEngine v3 domain config. Validate it before use:

```bash
# Validate from the command line via the API
curl -X POST http://localhost:8420/api/validate \
  -H 'Content-Type: application/json' \
  -d '{"config": <paste your JSON>}'
```

Or POST the config directly to `/api/simulate` with `{"config": {...}}` -- it will either run or return an error.

### Minimum Viable Config

The smallest config that will run:

```json
{
  "name": "Coin Flip",
  "n_simulations": 1000,
  "n_steps": 10,
  "parameters": {
    "heads": {
      "distribution": "bernoulli",
      "params": {"p": 0.5}
    }
  },
  "step_logic": [
    {"target": "payout", "expr": "1 if heads > 0.5 else -1"}
  ],
  "accumulators": {
    "bankroll": "bankroll + payout"
  },
  "metrics": {
    "final_bankroll": {"expr": "bankroll", "format": "number"}
  },
  "initial_state": {"bankroll": 0}
}
```

---

## Bayesian Updating

SimEngine supports conjugate Bayesian updates that tighten your parameter distributions as real-world data arrives.

### How It Works

1. You start with a prior -- the distribution you specified in the config (e.g., `triangular(0.02, 0.05, 0.12)` for churn rate).
2. You observe real data (e.g., actual monthly churn: `[0.04, 0.06, 0.03, 0.05]`).
3. The engine computes the posterior distribution using the appropriate conjugate update.
4. The config is rewritten with tighter distributions that reflect both your prior belief and the evidence.

### Supported Methods

| Method | Conjugate Pair | Use For |
|--------|---------------|---------|
| `beta_binomial` | Beta-Binomial | Rates and probabilities: close rate, churn rate, conversion rate |
| `gamma_poisson` | Gamma-Poisson | Counts: leads per month, bugs per sprint, signups per week |
| `normal_normal` | Normal-Normal | Continuous means: project value, salary, deal size |

### Method Selection

The method is chosen in this order:

1. Explicit `calibration.update_method` in the variable definition.
2. Auto-inferred from the distribution type and parameter range (values in [0,1] get Beta-Binomial; integer-valued Poisson gets Gamma-Poisson; everything else gets Normal-Normal).

### Via the API

```bash
curl -X POST http://localhost:8420/api/update \
  -H 'Content-Type: application/json' \
  -d '{
    "domain": "saas_startup.json",
    "observations": {
      "monthly_churn_rate": [0.04, 0.06, 0.03, 0.05]
    }
  }'
```

The response includes the updated config, a diagnostic report showing prior vs. posterior, and a preview simulation with the updated parameters.

### Via Python

```python
from bayesian import update_parameter

updated_params, diagnostics = update_parameter(
    variable_def={
        "distribution": "triangular",
        "params": {"low": 0.02, "mode": 0.05, "high": 0.12}
    },
    observations=[0.04, 0.06, 0.03, 0.05],
    method="beta_binomial"
)

print(diagnostics["posterior_mean"])    # 0.0459
print(diagnostics["credible_interval_90"])  # [0.0312, 0.0606]
```

---

## AI Agent Integration

SimEngine is designed to be used as a tool by LLMs and AI agents. The key feature is inline config support: POST a full domain config directly to `/api/simulate` without saving any files.

### The Pattern

1. The agent describes a problem as a SimEngine domain config (JSON).
2. The agent POSTs `{"config": {...}, "n_simulations": 5000, "seed": 42}` to `/api/simulate`.
3. The agent reads the structured response: stats, safety evaluation, fitness score, narrative.
4. The agent reasons about the results and either reports back or adjusts the config and re-runs.

### Example: Agent Tool Call

```python
import json, urllib.request

config = {
    "name": "Should I take this contract?",
    "n_simulations": 3000,
    "n_steps": 6,
    "step_label": "month",
    "parameters": {
        "hours_per_week": {
            "distribution": "triangular",
            "params": {"low": 15, "mode": 25, "high": 45}
        },
        "scope_creep": {
            "distribution": "bernoulli",
            "params": {"p": 0.3}
        }
    },
    "controls": {
        "hourly_rate": {
            "distribution": "fixed",
            "params": {"value": 150}
        }
    },
    "exogenous": {},
    "initial_state": {"total_hours": 0, "total_revenue": 0},
    "step_logic": [
        {"target": "weekly_hours", "expr": "hours_per_week * (1.4 if scope_creep > 0.5 else 1.0)"},
        {"target": "monthly_hours", "expr": "weekly_hours * 4.33"},
        {"target": "monthly_rev", "expr": "min(monthly_hours, 160) * hourly_rate"}
    ],
    "accumulators": {
        "total_hours": "total_hours + monthly_hours",
        "total_revenue": "total_revenue + monthly_rev"
    },
    "metrics": {
        "total_revenue": {"expr": "total_revenue", "format": "dollar"},
        "effective_rate": {"expr": "total_revenue / total_hours if total_hours > 0 else 0", "format": "dollar"},
        "total_hours": {"expr": "total_hours", "format": "number"}
    }
}

req = urllib.request.Request(
    "http://localhost:8420/api/simulate",
    data=json.dumps({"config": config, "seed": 42}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)
resp = json.loads(urllib.request.urlopen(req).read())

print(f"Revenue (median): ${resp['stats']['total_revenue']['median']:,.0f}")
print(f"Revenue (P10-P90): ${resp['stats']['total_revenue']['p10']:,.0f} - ${resp['stats']['total_revenue']['p90']:,.0f}")
print(f"Effective rate (median): ${resp['stats']['effective_rate']['median']:,.0f}/hr")
```

### What Agents Get Back

The `/api/simulate` response includes everything an agent needs to reason about the outcome:

- `stats` -- Full distribution statistics for every metric (mean, median, std, p10/p25/p75/p90), plus `ci95`: the Monte Carlo error on each of those estimates (and on `binary_prob` for indicator metrics).
- `safety` -- Pass/fail on every constraint with actual probabilities, a 95% interval on each chance-constraint probability, and a `borderline` flag when the limit falls inside it.
- `fitness` -- Single scalar score for comparing scenarios.
- `narrative` -- Human-readable summary text.
- `trajectories` -- Time-series percentile bands for trend analysis.
- `histograms` -- Binned data for distribution shape analysis.

### Scenario Comparison

To compare alternatives, an agent can POST multiple configs (varying the controls) and compare fitness scores, safety evaluations, or specific metric percentiles across the responses.

### Decision Gate: `decide_under_uncertainty` (MCP)

Multi-step agents compound overconfident point answers. The `decide_under_uncertainty` MCP tool turns a simulation into a **proceed / escalate** verdict: it runs the Monte Carlo, measures how much of the *outcome* distribution lands inside a range you accept, and returns the flag plus the full distribution and a plain-English reason.

It models **outcome risk** -- the spread of results given uncertain inputs -- not the language model's own token confidence. The two are complementary; do not conflate them.

**Arguments:** `metric` (required), `acceptable` (`{"min": ..., "max": ...}`, at least one bound), `min_confidence` (probability mass that must land in range to proceed, default 0.8), plus `domain` or inline `config`, and optional `seed` / `n_simulations`.

```json
{
  "metric": "annual_gross_income",
  "decision": "proceed",
  "proceed": true,
  "probability_within_bounds": 0.92,
  "min_confidence": 0.8,
  "acceptable": {"min": 40000, "max": null},
  "distribution": {"median": 68000, "p10": 44000, "p90": 95000, "format": "dollar"},
  "n_simulations": 5000,
  "reason": "92% of 5,000 simulated outcomes for 'annual_gross_income' fall within the acceptable range (>= 40,000) -- at or above the 80% confidence required to proceed."
}
```

See [`docs/decision-gate.md`](docs/decision-gate.md) for the full agent pattern.

---

## Calibration & Track Record

A Monte Carlo engine will always emit a confident-looking distribution. The only thing that separates *"a calculator that produces plausible numbers"* from *"a forecasting instrument with a demonstrated hit rate"* is a track record scored against reality. `v3/calibration.py` is that spine -- pure stdlib, zero dependencies.

**Proper scoring rules:** `brier_score`, `log_loss`, `crps_sample`.

**Forecast ledger:** record a forecast now, resolve it against the real outcome later, score how well-calibrated you have been over time.

```python
from calibration import CalibrationLedger

ledger = CalibrationLedger("forecasts.db")
fid = ledger.record("Annual gross >= $40k?", 0.82, metric="annual_gross_income")
# ... the year resolves ...
ledger.resolve(fid, 1)
print(ledger.score())   # {"n": 1, "brier": 0.0324, "log_loss": 0.198}
```

Brier 0.0 is perfect; 0.25 is the score of always guessing 50/50; 1.0 is worst. Log-loss punishes confident-and-wrong forecasts harder. Lower is better for both. Time is the moat: the track record only accumulates if logging starts now.

---

## Real-Time Data (opt-in)

The core engine is offline and pure-stdlib. The `v3/feeds/` package is the optional bridge to live data — the only part of SimEngine that touches the network, still using only `urllib` (no new dependencies), and never imported by the core.

The first adapter, `feeds/polymarket.py`, turns a live Polymarket prediction-market price into a **calibrated prior**: a market-implied probability becomes a SimEngine variable you can drop into a domain config and then tighten with the Beta-Binomial updater as your own evidence arrives. Price in → prior → posterior, not price in → price out.

```python
from feeds import polymarket
markets = polymarket.fetch_markets(query="fed rate", limit=5)
prior = polymarket.market_prior(markets[0], strength=20)   # -> a triangular variable_def
# or distribution="beta" for an exactly-updatable Beta(p*strength, (1-p)*strength) prior
```

See [`docs/feeds.md`](docs/feeds.md). Market prices are treated as internal simulation inputs, never a rebroadcast feed or trade signal.

---

## Ask SimEngine Anything (natural language)

Don't want to write a config? Describe your decision in plain words and let an LLM build the model for you. SimEngine drafts a config, validates it against the engine, **repairs** any errors, runs the simulation, and explains the result — so even small local models stay reliable, because the engine grounds whatever the model produces.

This is **opt-in** and stdlib-only. It defaults to a **local** model via [Ollama](https://ollama.com) — free, private, no API key. Set an environment variable to use a hosted model instead.

### CLI

```bash
# With Ollama running (e.g. `ollama pull qwen2.5`):
python3 v3/sim_ask.py "Should I take an $8k/mo, 6-month contract if there's a 30% chance it overruns?"
```

Flags: `--n` (simulations), `--seed`, `--save NAME` (persist the config to `domains/`), `--show-config`, `--json`, `--model NAME`, `--backend`.

### Web

Open `http://localhost:8420`, click **Ask anything**, type your question, and run. You get a plain-language answer, the key numbers, the safety verdict, and the generated model — which you can save as a reusable domain.

### API

`POST /api/ask` with `{"question": "...", "n_simulations": 3000, "seed": 42}` returns `{config, results, explanation, attempts, valid}`.

### Backends (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `SIMENGINE_LLM_BACKEND` | `ollama` | `ollama` \| `openai` \| `anthropic` |
| `SIMENGINE_LLM_MODEL` | `qwen2.5` | model name |
| `SIMENGINE_LLM_TIMEOUT` | `120` | per-request seconds (raise for slow local models) |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | — | OpenAI-compatible (also covers llama.cpp / LM Studio / vLLM) |
| `ANTHROPIC_API_KEY` | — | Anthropic |

Decision support and scenario analysis only — never financial advice or a trade signal.

---

## What the Numbers Mean

When you run a simulation, each metric reports:

- **Mean** -- Average across all simulated futures.
- **Median** -- The 50th percentile. Half of futures are above, half below.
- **P10** -- Pessimistic. Only 10% of futures are worse.
- **P90** -- Optimistic. Only 10% of futures are better.
- **Std** -- Standard deviation. Width of the distribution.
- **CVaR(alpha)** -- The average outcome in the worst alpha% of futures. This is the number that risk-aware decision makers care about most.

Safety constraints translate directly to decision language:

- **Chance constraint:** "The probability of [metric] falling [below/above] [threshold] must not exceed [X]%."
- **CVaR constraint:** "In the worst [alpha]% of scenarios, the average [metric] must be at least [min_cvar]."

---

## Documentation

**New to SimEngine? Start with the [plain-language guide](docs/guide/).** It explains what SimEngine is, how to read results, who it is for, how to explain it to others, and how to model your own decision — no background required.

Peer review reports and the system design paper are available on request. Contact the maintainer for access.

## License

SimEngine uses an **open-core** model.

- **Engine, server, kernels, diagnostics, Rust acceleration, and domain library** — [Apache License 2.0](LICENSE). Free to use, modify, self-host, embed in your own products, and redistribute under the terms of that license.
- **Hosted SimEngine MCP service** (operated by OtrovertLabs) — [Commercial license](LICENSE-COMMERCIAL.md). Subscription tiers for managed hosting, OAuth, persistent state, SLAs, and enterprise features.

Self-hosting the open-source engine is and will remain free. The commercial license applies only to the hosted service and managed features that are not part of the open-source distribution.

SimEngine is an **OtrovertLabs** product, published by Venture Horizon LLC.

For commercial licensing, enterprise inquiries, or partnerships: https://otrovertlabs.com/contact

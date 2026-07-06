# SimEngine v3 -- AI Agent Integration Guide

This document describes how an AI agent (LLM-based or otherwise) can consume the
SimEngine v3 API to build, run, interpret, and refine Monte Carlo simulation models
on behalf of a user.

**Base URL:** `http://localhost:8420`

**OpenAPI spec:** See `openapi.yaml` in this directory for the full machine-readable
schema.

---

## Table of Contents

1. [Overview: What an Agent Can Do](#1-overview-what-an-agent-can-do)
2. [Generating a Domain Config from Natural Language](#2-generating-a-domain-config-from-natural-language)
3. [Worked Example: "Model My Food Truck Revenue"](#3-worked-example-model-my-food-truck-revenue)
4. [Interpreting Simulation Results](#4-interpreting-simulation-results)
5. [Bayesian Updates with Real Data](#5-bayesian-updates-with-real-data)
6. [Curl Examples for Every Endpoint](#6-curl-examples-for-every-endpoint)

---

## 1. Overview: What an Agent Can Do

The SimEngine API allows an agent to follow this workflow:

1. **Translate** a user's natural-language scenario into a structured domain config JSON.
2. **Validate** the config before running it.
3. **Simulate** to produce statistical results, trajectories, and safety evaluations.
4. **Interpret** the results back into plain language for the user.
5. **Refine** the model by adjusting parameters, adding constraints, or applying Bayesian updates with real data.
6. **Optimize** by running evolutionary search over tunable parameters.
7. **Report** by generating a standalone HTML report.

All endpoints accept and return JSON (except `/api/report` which returns HTML).

---

## 2. Generating a Domain Config from Natural Language

When a user describes a scenario in plain language, the agent should decompose it
into the following structural elements:

### Step-by-step translation process

**A. Identify the decision context**

Extract from the user's description:
- What decision are they trying to make? --> `context.decision`
- What can they control? --> `context.key_levers`
- What does success look like? --> `context.what_good_looks_like`

**B. Identify variables and classify them**

Every uncertain quantity falls into one of three categories:

| Category       | Field          | Meaning                                    |
|----------------|----------------|--------------------------------------------|
| `parameters`   | Uncertain inputs | Things you do not know precisely (demand, conversion rates) |
| `controls`     | Decision levers  | Things you set (price, staff count, budget) |
| `exogenous`    | External factors | Things outside your control (weather, competitors, regulation) |

**C. Choose distributions**

For each variable, pick a distribution based on what the user knows:

| User says...                          | Distribution to use                        |
|---------------------------------------|-------------------------------------------|
| "exactly 10"                          | `fixed({value: 10})`                      |
| "between 5 and 15"                    | `uniform({low: 5, high: 15})`             |
| "around 10, could be 5-15"           | `triangular({low: 5, mode: 10, high: 15})` |
| "about 100 give or take 20"          | `normal({mean: 100, std: 20})`            |
| "typically 50 but sometimes much more"| `lognormal({median: 50, spread: 1.5})`    |
| "happens 30% of the time"            | `bernoulli({p: 0.3})`                     |
| "about 5 events per day"             | `poisson({lambda: 5})`                    |
| "around 100, heavy tails"            | `student_t({mean: 100, scale: 20, df: 3})`|

Always add a `calibration` string explaining the reasoning.

**D. Define the time structure**

- `n_steps`: How many time periods to simulate (e.g., 12 for monthly over a year).
- `step_label`: Human label for each step (e.g., "Month", "Week", "Day").
- If the model has no time dimension, use `n_steps: 1`.

**E. Write step logic**

`step_logic` is an ordered list of `{target, expr}` entries evaluated each step.
Expressions can reference:
- Any variable name from parameters, controls, or exogenous
- The special variable `step` (0-indexed step counter)
- State variables set by previous step_logic entries in the same step
- Accumulator values carried from the previous step
- Safe builtins: `min, max, abs, round, sum, len, int, float, sqrt, log, exp, ceil, floor, pow, random, gauss, binomial, clamp, range`

**F. Define accumulators**

Accumulators carry state across steps. Each is an expression that typically adds
the current step's value to the running total. Example:

```json
"accumulators": {
  "total_revenue": "total_revenue + revenue",
  "total_cost": "total_cost + cost"
}
```

Set their starting values in `initial_state`.

**G. Define metrics**

Metrics are the final outputs computed once per simulation after all steps complete.
They reference accumulator values or final state. Each metric has an `expr` and
an optional `format` ("dollar", "number", or "percent").

**H. Define safety constraints (optional)**

Safety constraints define what "not acceptable" looks like:
- **Chance constraints**: "The probability of losing more than $50k must be below 10%."
- **CVaR constraints**: "The average loss in the worst 5% of cases must not exceed $100k."

**I. Define fitness and tunables (optional)**

If the user wants optimization, define:
- `fitness.components`: What to maximize (weighted sum of expressions over metrics).
- `tunable`: Which parameter paths the optimizer can adjust and their allowed ranges.

---

## 3. Worked Example: "Model My Food Truck Revenue"

### User prompt

> "I'm thinking about starting a food truck. I'd sell tacos for about $8 each.
> On a good day I might get 80 customers, but it could be as low as 30 on a bad
> day, and typically around 55. My food cost is roughly 35% of revenue. I'd have
> about $800/month in fixed costs -- parking, insurance, gas. I want to model
> 12 months. I'm worried about months where I lose money."

### Agent's translation

The agent constructs the following config:

```json
{
  "name": "Food Truck Revenue",
  "description": "12-month projection for a taco food truck",
  "n_simulations": 2000,
  "n_steps": 12,
  "step_label": "Month",
  "context": {
    "decision": "Whether to start a taco food truck business",
    "key_levers": "Taco price, operating days per month",
    "what_good_looks_like": "Consistent monthly profit with low chance of losing money"
  },
  "parameters": {
    "daily_customers": {
      "distribution": "triangular",
      "params": {"low": 30, "mode": 55, "high": 80},
      "calibration": "User estimates 30-80 customers per day, typically 55"
    },
    "food_cost_pct": {
      "distribution": "normal",
      "params": {"mean": 0.35, "std": 0.05, "min": 0.20, "max": 0.50},
      "calibration": "Roughly 35% of revenue, with some variance in ingredient costs"
    },
    "operating_days": {
      "distribution": "triangular",
      "params": {"low": 20, "mode": 24, "high": 26},
      "calibration": "Typical working days per month accounting for weather and maintenance"
    }
  },
  "controls": {
    "taco_price": {
      "distribution": "fixed",
      "params": {"value": 8},
      "calibration": "User's planned price point"
    }
  },
  "exogenous": {
    "bad_weather_pct": {
      "distribution": "uniform",
      "params": {"low": 0.0, "high": 0.20},
      "calibration": "Fraction of days with weather bad enough to reduce traffic"
    }
  },
  "initial_state": {
    "total_revenue": 0,
    "total_cost": 0,
    "months_negative": 0
  },
  "step_logic": [
    {"target": "effective_days", "expr": "operating_days * (1 - bad_weather_pct)"},
    {"target": "monthly_customers", "expr": "daily_customers * effective_days"},
    {"target": "revenue", "expr": "monthly_customers * taco_price"},
    {"target": "food_cost", "expr": "revenue * food_cost_pct"},
    {"target": "fixed_cost", "expr": "800"},
    {"target": "cost", "expr": "food_cost + fixed_cost"},
    {"target": "profit", "expr": "revenue - cost"},
    {"target": "is_negative", "expr": "1 if profit < 0 else 0"}
  ],
  "accumulators": {
    "total_revenue": "total_revenue + revenue",
    "total_cost": "total_cost + cost",
    "months_negative": "months_negative + is_negative"
  },
  "metrics": {
    "annual_revenue": {"expr": "total_revenue", "format": "dollar"},
    "annual_cost": {"expr": "total_cost", "format": "dollar"},
    "annual_profit": {"expr": "total_revenue - total_cost", "format": "dollar"},
    "months_in_red": {"expr": "months_negative", "format": "number"},
    "profit_margin": {"expr": "(total_revenue - total_cost) / total_revenue", "format": "percent"}
  },
  "safety": {
    "chance_constraints": [
      {
        "metric": "annual_profit",
        "condition": "<",
        "threshold": 0,
        "max_prob": 0.10
      }
    ],
    "cvar_constraints": [
      {
        "metric": "annual_profit",
        "alpha": 0.05,
        "min_cvar": -5000
      }
    ]
  },
  "fitness": {
    "components": [
      {"expr": "annual_profit", "weight": 1.0, "name": "Maximize profit"}
    ]
  },
  "tunable": [
    {
      "path": "controls.taco_price.params.value",
      "range": [6, 12]
    }
  ]
}
```

### Agent validates and runs

```bash
# Validate the config first
curl -s -X POST http://localhost:8420/api/validate \
  -H "Content-Type: application/json" \
  -d '{"config": <CONFIG_JSON>}'

# If valid, run the simulation
curl -s -X POST http://localhost:8420/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"config": <CONFIG_JSON>}'
```

---

## 4. Interpreting Simulation Results

The `/api/simulate` response contains several sections. Here is how an agent should
interpret each one and relay it to the user.

### 4.1 stats

A dictionary keyed by metric name. Each entry contains:

| Field    | Meaning                                          |
|----------|--------------------------------------------------|
| `mean`   | Average across all simulations                   |
| `median` | 50th percentile (typical outcome)                |
| `std`    | Standard deviation (spread of outcomes)          |
| `p5`     | 5th percentile (bad-case scenario)               |
| `p25`    | 25th percentile (below-average outcome)          |
| `p75`    | 75th percentile (above-average outcome)          |
| `p95`    | 95th percentile (best-case scenario)             |
| `min`    | Worst single simulation                          |
| `max`    | Best single simulation                           |

**Agent interpretation pattern:** "Your median annual profit is $X. In a bad year
(5th percentile), you might see $Y. In a great year (95th percentile), $Z."

### 4.2 safety

Reports whether each constraint passed or failed:

- **Chance constraints** show the observed probability of violation vs. the maximum
  allowed. If `observed_prob > max_prob`, the constraint failed.
- **CVaR constraints** show the conditional value at risk in the specified tail.
  If `observed_cvar < min_cvar`, the constraint failed.

**Agent interpretation pattern:** "There is a 7% chance of ending the year at a
loss, which is within your 10% tolerance. However, in the worst 5% of scenarios,
the average loss is $8,200 -- this exceeds your $5,000 limit, so you may want
to build in more margin."

### 4.3 trajectories

Step-by-step data for accumulators showing how values evolve over time. Contains
percentile bands (p5, p25, p50, p75, p95) at each step. Useful for telling the
user things like "By month 6, your cumulative revenue is typically around $X."

### 4.4 histograms

Bin edges and counts for each metric. Useful if the agent wants to describe the
shape of the distribution: "The profit distribution is slightly left-skewed,
with a long tail of bad outcomes."

### 4.5 fitness

A single scalar score. Higher is better. Only meaningful when a fitness function
is defined. Useful for comparing different configurations.

### 4.6 narrative

A pre-generated human-readable summary. The agent can use this directly or
rephrase it for the user.

### 4.7 context

Echo of the context object from the config, useful for framing the response.

---

## 5. Bayesian Updates with Real Data

After the initial simulation, the user may collect real-world data. The Bayesian
update endpoint shifts prior distributions toward posteriors that better reflect
observed reality.

### Workflow

1. User runs the food truck for a few weeks and reports actual daily customer counts.
2. Agent sends these observations to `/api/update`.
3. The API returns an updated config with posterior distributions and a preview
   of how the simulation results change.
4. Agent explains what shifted and re-runs the simulation if needed.

### Example

The user says: "I've been open for two weeks. My daily customer counts were:
42, 55, 38, 61, 47, 52, 44, 58, 39, 50."

The agent calls:

```bash
curl -s -X POST http://localhost:8420/api/update \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "food_truck.json",
    "observations": {
      "daily_customers": [42, 55, 38, 61, 47, 52, 44, 58, 39, 50]
    }
  }'
```

### Interpreting the update response

The `update_report` shows, for each variable that was updated:

- **Prior**: The original distribution and its parameters.
- **Posterior**: The new distribution after incorporating the data.
- **Shift summary**: How the central tendency and spread changed.

Example interpretation for the user:

> "Based on your first 10 days of data (mean: 48.6 customers/day), the model
> has updated its estimate. The original assumption was a triangular distribution
> centered on 55, but the data suggests a slightly lower typical day. The
> updated model centers on about 49 customers/day with a tighter range. Your
> projected annual profit dropped from $42,000 to $36,500 at the median, but
> the risk of a losing year is still only 8%."

The agent can then save the updated config and use it going forward:

```bash
curl -s -X POST http://localhost:8420/api/save-domain \
  -H "Content-Type: application/json" \
  -d '{"config": <UPDATED_CONFIG>, "filename": "food_truck_updated.json"}'
```

---

## 6. Curl Examples for Every Endpoint

### Health check

```bash
curl -s http://localhost:8420/api/health
# {"status": "ok", "engine": "simengine-v3", ...}
```

### List all domains

```bash
curl -s http://localhost:8420/api/domains | python3 -m json.tool
```

### Get a specific domain config

```bash
curl -s http://localhost:8420/api/domain/food_truck.json | python3 -m json.tool
```

### Validate a config

```bash
curl -s -X POST http://localhost:8420/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "name": "Test",
      "parameters": {
        "x": {"distribution": "normal", "params": {"mean": 10, "std": 2}}
      },
      "step_logic": [{"target": "y", "expr": "x * 2"}],
      "metrics": {"result": {"expr": "y", "format": "number"}}
    }
  }'
```

### Run a simulation with inline config

```bash
curl -s -X POST http://localhost:8420/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "name": "Coin Flip",
      "n_simulations": 5000,
      "parameters": {
        "flip": {"distribution": "bernoulli", "params": {"p": 0.5}}
      },
      "step_logic": [
        {"target": "payout", "expr": "100 if flip else -50"}
      ],
      "metrics": {
        "payout": {"expr": "payout", "format": "dollar"}
      }
    }
  }' | python3 -m json.tool
```

### Run a simulation from a saved domain

```bash
curl -s -X POST http://localhost:8420/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "food_truck.json",
    "n_simulations": 5000
  }' | python3 -m json.tool
```

### Run a simulation with overrides

```bash
curl -s -X POST http://localhost:8420/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "food_truck.json",
    "overrides": {
      "controls": {
        "taco_price": {"distribution": "fixed", "params": {"value": 10}}
      }
    },
    "n_simulations": 3000
  }' | python3 -m json.tool
```

### Save a domain config

```bash
curl -s -X POST http://localhost:8420/api/save-domain \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "name": "My Model",
      "parameters": {"x": {"distribution": "normal", "params": {"mean": 5, "std": 1}}},
      "step_logic": [{"target": "y", "expr": "x * 3"}],
      "metrics": {"output": {"expr": "y", "format": "number"}}
    },
    "filename": "my_model.json"
  }'
```

### Bayesian update with observations

```bash
curl -s -X POST http://localhost:8420/api/update \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "food_truck.json",
    "observations": {
      "daily_customers": [42, 55, 38, 61, 47, 52, 44, 58, 39, 50]
    }
  }' | python3 -m json.tool
```

### Evolutionary optimization

```bash
curl -s -X POST http://localhost:8420/api/evolve \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "food_truck.json",
    "generations": 25,
    "population": 40
  }' | python3 -m json.tool
```

### Generate HTML report

```bash
# First run a simulation and capture results
RESULTS=$(curl -s -X POST http://localhost:8420/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"domain": "food_truck.json"}')

CONFIG=$(curl -s http://localhost:8420/api/domain/food_truck.json)

# Then generate the report
curl -s -X POST http://localhost:8420/api/report \
  -H "Content-Type: application/json" \
  -d "{\"results\": $RESULTS, \"config\": $CONFIG}" \
  -o report.html
```

---

## Appendix: Quick Reference for Distribution Selection

| Distribution   | Params                                    | Use when...                                      |
|----------------|-------------------------------------------|--------------------------------------------------|
| `fixed`        | `{value}`                                 | Value is known exactly                           |
| `uniform`      | `{low, high}`                             | Equally likely anywhere in a range               |
| `triangular`   | `{low, mode, high}`                       | You know the likely value and bounds             |
| `normal`       | `{mean, std, min?, max?}`                 | Symmetric uncertainty around a central value     |
| `lognormal`    | `{median, spread, min?, max?}`            | Right-skewed, always positive                    |
| `bernoulli`    | `{p}`                                     | Yes/no event with known probability              |
| `poisson`      | `{lambda}`                                | Count of events per time period                  |
| `student_t`    | `{mean?, scale?, df?, min?, max?}`        | Like normal but with heavier tails               |

## Appendix: Safe Builtins for Expressions

These functions are available in `step_logic` expressions, `accumulator` expressions,
`metric` expressions, and `fitness` expressions:

`min`, `max`, `abs`, `round`, `sum`, `len`, `int`, `float`, `sqrt`, `log`, `exp`,
`ceil`, `floor`, `pow`, `random`, `gauss`, `binomial`, `clamp`, `range`

The special variable `step` is available in step_logic and holds the 0-indexed
step number.

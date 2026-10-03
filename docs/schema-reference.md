# SimEngine v3 Domain Config — Schema Reference

A domain config is a single JSON object. It declares the variables that feed a
simulation, the per-step logic that advances state, and the metrics you read off
the result. The engine samples those variables thousands of times, runs the logic
forward `n_steps` per simulation, and reports the distribution of each metric.

This document is the hand-authoring guide: every field, every distribution, every
sub-shape, in plain language. It describes what the code actually does, not what
an idealized schema might allow.

A field is **required** only if `validate_config` rejects the config without it.
Everything else has a working default in `DomainConfig`, even when the README or
template implies otherwise.

---

## Top-level fields

### Required

| Field | Type | What it does |
|-------|------|--------------|
| `name` | string | Config name. Validation rejects an empty/falsy value (`Missing name field`). `DomainConfig` would default it to `"unnamed"`, but validation makes it mandatory. |
| `n_steps` | integer | Number of steps per simulation. Must be an integer `>= 1` (`n_steps must be a positive integer`). |
| `metrics` | object | Map of `metricName -> {expr, format?}`. Required and non-empty (`Missing metrics`). See [Metrics](#metrics). |
| `step_logic` | array | Ordered list of state updates run each step. Required and non-empty (`Missing step_logic`). See [step_logic](#step_logic). |

Plus an **at-least-one-variable-category** rule: at least one of `parameters`,
`controls`, or `exogenous` must be present and non-empty, or validation fails with
`No variables defined`. (`variables` does **not** satisfy this — see below.)

### Variable categories

All three share the same [variable definition shape](#variable-definition-shape).
They differ only in intent and in how the UI and optimizer treat them.

| Field | Type | What it means |
|-------|------|---------------|
| `parameters` | object | Uncertain quantities you don't control (conversion rate, churn, cost). |
| `controls` | object | Decisions the operator makes (price, budget, hiring). These are what the optimizer is allowed to tune. |
| `exogenous` | object | External shocks outside anyone's control (market swings, seasonality, weather). |
| `variables` | object | **Legacy / backward-compat only.** It is resolvable in expressions, and `DomainConfig` merges it into `parameters` when `parameters` is empty. But `validate_config`'s "at least one category" check ignores it — a config whose only variables live under `variables` will fail validation even though the kernel could run it. Use `parameters` instead. |

### Optional metadata and behavior

| Field | Type | Default | What it does |
|-------|------|---------|--------------|
| `description` | string | `""` | Free text. |
| `n_simulations` | integer | `5000` | Monte Carlo run count. Not validated. |
| `step_label` | string | `"step"` | Time-axis label for the UI (`"month"`, `"week"`, `"sprint"`). |
| `seed` | integer / null | `null` | Random seed for reproducibility. |
| `initial_state` | object | `{}` | Starting values for accumulators and step targets. Map of `name -> number`. Each name becomes a valid expression reference. |
| `accumulators` | object | `{}` | Map of `name -> expression string`, evaluated every step to maintain running totals. Auto-initialized to `0.0` unless seeded in `initial_state`. See [Accumulators](#accumulators). |
| `safety` | object | `{}` | Risk constraints. `{chance_constraints?, cvar_constraints?}`. Not structurally validated; consumed at evaluation time. See [Safety](#safety). |
| `fitness` | object | `{}` | Optimizer objective. `{components: [...]}`. See [Fitness](#fitness). |
| `tunable` | array | `[]` | Paths the optimizer may mutate, with bounds. See [Tunable](#tunable). |
| `correlations` | array | `[]` | v3.1: pairwise correlations between variables. See [Correlations](#correlations). |
| `calibration` | object | `{}` | Calibration metadata. Read at top level by `DomainConfig`, but in practice it's almost always attached **per variable**, not here — see the variable shape below. |
| `context` | object | — | Optional metadata (decision question, key levers). Passed through in API responses; not read by the engine or validator. |
| `_guide` | object | — | Documentation-only field used in `_template.json`. Ignored by the engine. |

---

## Variable definition shape

Every entry under `parameters`, `controls`, `exogenous`, and `variables` looks the
same:

```json
{
  "distribution": "<one of the distribution names>",
  "params": { "...": "..." },
  "calibration": { }
}
```

- `distribution` (required) must be one of the [distribution names](#distributions). An unknown name is rejected (`unknown distribution`).
- `params` (required) must be a non-empty object. Missing or empty is rejected (`missing params`).
- `calibration` (optional) is per-variable metadata. Carried through; not structurally validated.

**Late-binding references.** A param value may be a numeric literal *or* a string
beginning with `$`. At sample time, `$name` resolves to the current value of `name`
in simulation state (`state.get(name, 0)`). This lets a distribution depend on
something computed earlier in the run. Note: any `$`-prefixed or non-numeric param
forces the engine off its native batch sampler and back to the Python path (so does
any use of `correlations`).

---

## Distributions

Eight samplers are registered. The param keys below are the exact keys the kernel
reads — spell them precisely.

| Distribution | Required params | Optional params | Use when |
|--------------|-----------------|-----------------|----------|
| `fixed` | `value` | — | The quantity is a known constant, not uncertain. |
| `uniform` | `low`, `high` | — | Any value in a range is equally plausible; you only know the bounds. |
| `triangular` | `low`, `high`, `mode` | — | You have a min, a max, and a single most-likely value. |
| `normal` | `mean`, `std` | `min`, `max` | A symmetric bell around a center; optionally clamp the tails. |
| `lognormal` | `median`, `spread` | `min`, `max` | A positive, right-skewed quantity (revenue, time, multipliers). |
| `bernoulli` | `p` | — | A yes/no event with probability `p` (returns 0 or 1). |
| `poisson` | `lambda` | — | A count of independent events in a period (arrivals, defects). |
| `student_t` | *(none)* | `df`, `mean`, `scale`, `min`, `max` | A bell with heavier tails than normal — fat-tail risk. |

Exact sampler behavior (so you author params correctly):

- **`fixed`** → returns `value`.
- **`uniform`** → draws between `low` and `high`.
- **`triangular`** → `random.triangular(low, high, mode)`. Supply all three keys: `low`, `mode`, `high`.
- **`normal`** → `gauss(mean, std)`, then clamped to `[min, max]` with defaults `min=-1e18`, `max=1e18`.
- **`lognormal`** → built from `log(median)` and `spread`; clamped to `[min, max]` with defaults `min=0`, `max=1e18`. `median` must be positive.
- **`bernoulli`** → 1 with probability `p`, else 0.
- **`poisson`** → integer count with rate `lambda`.
- **`student_t`** → defaults `df=5`, `mean=0`, `scale=1`, clamped with `min=-1e18`, `max=1e18`. Every param has a default, so `student_t` has no strictly-required key — but always set `df`/`mean`/`scale` deliberately.

> **Not a distribution: `correlated_normal`.** Older README tables list it as a
> ninth distribution. It is **not** in the sampler registry, so `validate_config`
> rejects it as an unknown distribution. Express correlation through the top-level
> [`correlations`](#correlations) array applied to ordinary distributions instead.

---

## step_logic

An ordered array of state updates, run top to bottom on every step. Each item:

```json
{ "target": "leads", "expr": "visitors * conversion_rate" }
```

or

```json
{ "target": "churned", "sample": { "distribution": "poisson", "params": { "lambda": 3 } } }
```

- `target` (required) — a non-empty string naming the state variable to write. Missing → `step_logic[i]: missing target`.
- Exactly one of:
  - `expr` — an [expression string](#expressions) evaluated against current state.
  - `sample` — an inline variable def (`{distribution, params}`) drawn fresh each step.
- Neither present → `step_logic[i]: missing expr or sample`.
- If **both** are present, the kernel uses `expr` (it checks for `expr` first). Don't rely on this — supply one.

Targets you write here become valid names in later expressions, accumulators, and
metrics. The current 1-based step index is available as `_step`.

---

## Accumulators

A map of `name -> expression string`, evaluated once per step **after** step_logic,
to carry running totals across the whole simulation.

```json
"accumulators": {
  "total_revenue": "total_revenue + revenue",
  "peak_users": "max(peak_users, active_users)"
}
```

- Each value must be an expression string.
- Each accumulator auto-initializes to `0.0` unless you give it a starting value in `initial_state`.
- Accumulator names are valid references in expressions and metrics — that's how most metrics read final totals.

---

## Metrics

A map of `metricName -> {expr, format?}`. Each metric is computed per simulation,
then summarized into a distribution across all simulations.

```json
"metrics": {
  "total_revenue": { "expr": "total_revenue", "format": "dollar" },
  "ending_users":  { "expr": "active_users",  "format": "number" }
}
```

- `expr` (required) — the expression evaluated for this metric.
- `format` (optional) — display hint, default `"number"`. Recognized: `"number"`, `"dollar"`, `"percent"`.

A metric whose mean comes back `NaN` in the validation test run is flagged as an
error.

---

## Safety

Optional risk constraints, evaluated against the simulated metric distributions.
Two kinds, both optional:

### `chance_constraints`

"The probability of a bad outcome must stay under a ceiling."

```json
{
  "metric": "ending_cash",
  "condition": "below",
  "threshold": 0,
  "max_prob": 0.05,
  "rationale": "Don't run out of cash"
}
```

- `metric` — metric name to test.
- `condition` — `"below"` counts outcomes where `value < threshold`; any other value counts `value > threshold`.
- `threshold` — the line.
- `max_prob` — maximum allowed probability (0..1) of crossing it.
- `rationale` (optional) — free text.

All four core keys are effectively required: the evaluator reads them directly,
without defaults.

### `cvar_constraints`

"The average of the worst cases must not be too bad." (Conditional Value at Risk.)

```json
{
  "metric": "ending_cash",
  "alpha": 0.10,
  "min_cvar": -5000,
  "rationale": "Even the worst 10% shouldn't average below -$5k"
}
```

- `metric` — metric name.
- `alpha` — tail fraction (e.g. `0.10` = worst 10%).
- `min_cvar` — minimum acceptable CVaR. CVaR is the mean of the lowest `alpha`-fraction of outcomes; the constraint passes if `actual_cvar >= min_cvar`.
- `rationale` (optional).

`metric`, `alpha`, and `min_cvar` are effectively required.

---

## Fitness

The optimizer's objective. A weighted sum of components the optimizer tries to
maximize.

```json
"fitness": {
  "components": [
    { "name": "profit",  "expr": "total_revenue_median", "weight": 1.0 },
    { "name": "risk",    "expr": "0 - ending_cash_p10",  "weight": 0.5 }
  ]
}
```

- `components` — list of objects, each:
  - `expr` (required) — references **metric statistics**, not raw metrics, by the pattern `{metricName}_{stat}` where `stat` is one of `mean`, `median`, `std`, `p10`, `p25`, `p75`, `p90`. So `total_revenue_median`, `ending_cash_p10`, etc.
  - `weight` (optional) — default `1.0`.
  - `name` (optional) — label for reporting.

---

## Tunable

The list of config paths the optimizer is allowed to mutate, each with a numeric
range.

```json
"tunable": [
  { "path": "controls.price.params.value",          "range": [29, 99] },
  { "path": "controls.monthly_budget.params.value",  "range": [1000, 10000] }
]
```

- `path` (required) — a dot-separated path walked into the config dict. `controls.price.params.value` means "the `value` key inside `params` of the `price` control."
- `range` (required) — a 2-element `[lo, hi]` numeric array.

Both keys are effectively required.

---

## Correlations

v3.1. Inject statistical dependence between variables that would otherwise be
sampled independently.

```json
"correlations": [
  { "vars": ["conversion_rate", "market_demand"], "rho": 0.6 }
]
```

- `vars` — a 2-element list of variable names. Only pairs (`len == 2`) whose names are in the matrix are applied.
- `rho` — correlation coefficient (defaults to `0` if missing).

The engine builds a correlation matrix and Cholesky factor and applies it to the
samples. **Presence of any `correlations` entry disables the native batch sampler**
(the run falls back to the Python path).

---

## Expressions

Used in `step_logic` exprs, accumulator exprs, and metric exprs. A static name
checker runs before simulation to catch silent-zero bugs, because `eval_expr`
swallows runtime errors and returns `0` — a typo'd name would otherwise quietly
zero out a result instead of erroring.

### Allowed names

- The safe builtins below.
- `True`, `False`, `None`.
- `_step` — the current 1-based step index.
- Every variable name (`parameters` / `controls` / `exogenous` / `variables`).
- Every accumulator name.
- Every key in `initial_state`.
- Every `step_logic` target.

### Built-in functions and values

`min`, `max`, `abs`, `round`, `sum`, `len`, `int`, `float`, `sqrt`, `log`, `exp`,
`ceil`, `floor`, `pow`, `range`, `random` (= `random.random`), `gauss`
(= `random.gauss`), `binomial`, `clamp`, plus `True`, `False`.

`clamp(x, lo, hi)` bounds a value to a range. `binomial(n, p)` draws a binomial
count.

### Allowed syntax

Arithmetic, comparisons, and the ternary form `A if C else B`.

### Not allowed (rejected)

- Lambdas.
- Comprehensions (list / set / dict / generator).
- Attribute / dotted access (`x.y`).
- Subscripts (`x[0]`), walrus, starred, f-strings.
- Names beginning with `__`.
- Any name not in the allowed set above.

The syntax rules are enforced by the kernel itself when a config loads
(`DomainConfig` raises `ValueError`; the HTTP API answers 400, MCP tools return
an error), not only by `validate_config`. Unknown names are a validator-only
check: the kernel evaluates them to 0.

---

## Validation, briefly

`validate_config` runs static checks first (required fields, distribution names,
expression names, shapes). If those pass, it does a **live 10-iteration test run**
(seed `42`). It flags any metric whose mean is `NaN`, and surfaces runtime errors
as `Test run failed: <exc>`. A config that is schema-valid can still fail this
runtime check — for example, a `log` of a negative draw or a divide that blows up.

---

## Examples

### Minimal valid config

One uncertain parameter, one step, one metric.

```json
{
  "name": "coin_flips",
  "n_steps": 10,
  "parameters": {
    "heads": { "distribution": "bernoulli", "params": { "p": 0.5 } }
  },
  "accumulators": {
    "total_heads": "total_heads + heads"
  },
  "step_logic": [
    { "target": "flip", "sample": { "distribution": "bernoulli", "params": { "p": 0.5 } } }
  ],
  "metrics": {
    "total_heads": { "expr": "total_heads", "format": "number" }
  }
}
```

### Richer config

A SaaS-style model with a control, an exogenous shock, accumulators, a safety
constraint, a fitness objective, and a tunable.

```json
{
  "name": "saas_growth",
  "description": "Monthly subscriber and revenue model under a fixed price.",
  "n_steps": 12,
  "step_label": "month",
  "n_simulations": 5000,
  "seed": 42,
  "initial_state": { "active_users": 200, "cash": 50000 },

  "controls": {
    "price": { "distribution": "fixed", "params": { "value": 49 } }
  },
  "parameters": {
    "conversion_rate": { "distribution": "triangular", "params": { "low": 0.02, "mode": 0.04, "high": 0.07 } },
    "monthly_churn":   { "distribution": "normal",     "params": { "mean": 0.05, "std": 0.01, "min": 0, "max": 0.2 } },
    "new_visitors":    { "distribution": "poisson",    "params": { "lambda": 1500 } }
  },
  "exogenous": {
    "demand_shock": { "distribution": "lognormal", "params": { "median": 1.0, "spread": 0.15, "min": 0.5, "max": 2.0 } }
  },

  "step_logic": [
    { "target": "new_users",    "expr": "new_visitors * conversion_rate * demand_shock" },
    { "target": "churned",      "expr": "active_users * monthly_churn" },
    { "target": "active_users", "expr": "max(0, active_users + new_users - churned)" },
    { "target": "revenue",      "expr": "active_users * price" },
    { "target": "cash",         "expr": "cash + revenue - 20000" }
  ],

  "accumulators": {
    "total_revenue": "total_revenue + revenue"
  },

  "metrics": {
    "total_revenue": { "expr": "total_revenue", "format": "dollar" },
    "ending_users":  { "expr": "active_users",  "format": "number" },
    "ending_cash":   { "expr": "cash",          "format": "dollar" }
  },

  "correlations": [
    { "vars": ["conversion_rate", "demand_shock"], "rho": 0.4 }
  ],

  "safety": {
    "chance_constraints": [
      { "metric": "ending_cash", "condition": "below", "threshold": 0, "max_prob": 0.05,
        "rationale": "Stay solvent in at least 95% of futures" }
    ],
    "cvar_constraints": [
      { "metric": "ending_cash", "alpha": 0.10, "min_cvar": 0,
        "rationale": "Even the worst 10% of months should not end below zero on average" }
    ]
  },

  "fitness": {
    "components": [
      { "name": "revenue", "expr": "total_revenue_median", "weight": 1.0 },
      { "name": "safety",  "expr": "ending_cash_p10",       "weight": 0.5 }
    ]
  },

  "tunable": [
    { "path": "controls.price.params.value", "range": [29, 99] }
  ]
}
```

---

## Machine-readable schema

The authoritative, machine-readable schema is served at `/api/schema`. Use this
document to author by hand or to direct an AI; use `/api/schema` for programmatic
validation and tooling.

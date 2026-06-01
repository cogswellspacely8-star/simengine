# The Agent Decision Gate

`decide_under_uncertainty` is an MCP tool that gives an LLM agent a real
outcome-distribution calculator and a **proceed / escalate** flag. Use it to
stop a multi-step agent from acting on an overconfident point estimate.

## The problem it solves

An agent that reasons in single numbers ("this pricing change nets ~$12k/mo")
compounds error at every step. The number looks authoritative whether the
inputs were sound or fabricated. `decide_under_uncertainty` replaces the point
estimate with the **shape** of the outcome and a decision rule: does enough of
the distribution land inside the range you can live with?

It models **outcome risk** — the spread of results given uncertain inputs. It
does **not** measure the language model's own token confidence. Say "outcome
risk," never "model confidence."

## Contract

| Field | Required | Meaning |
|-------|----------|---------|
| `metric` | yes | The output metric to judge the decision on |
| `acceptable` | yes | `{"min": ..., "max": ...}` — supply at least one bound |
| `min_confidence` | no | Probability mass that must fall in range to proceed (default `0.8`) |
| `domain` / `config` | one of | Domain filename, or an inline config object |
| `seed`, `n_simulations` | no | Reproducibility and sample-size overrides |

Returns: `decision` (`"proceed"`/`"escalate"`), `proceed` (bool),
`probability_within_bounds`, the full `distribution` stats, and a plain-English
`reason`.

## Pattern: confidence-gated escalation

```jsonc
// Agent is about to commit to a SaaS pricing change. Before acting, it asks:
{
  "config": { /* inline SimEngine domain modeling the pricing change */ },
  "metric": "ending_cash",
  "acceptable": {"min": 0},          // never want to run out of cash
  "min_confidence": 0.85
}
```

- **proceed** → the agent acts: ≥85% of simulated futures keep `ending_cash`
  non-negative.
- **escalate** → the agent stops and asks a human, gathers more data, or picks
  a safer action. The `reason` tells it why and the `distribution` tells it how
  bad the tail is.

## Worked example (escalate)

```json
{
  "metric": "ending_cash",
  "decision": "escalate",
  "proceed": false,
  "probability_within_bounds": 0.61,
  "min_confidence": 0.85,
  "acceptable": {"min": 0, "max": null},
  "distribution": {"median": 8200, "p10": -4100, "p90": 21000, "format": "dollar"},
  "n_simulations": 5000,
  "reason": "Only 61% of 5,000 simulated outcomes for 'ending_cash' fall within the acceptable range (>= 0); the 85% confidence required to proceed is not met. Escalate or gather more data."
}
```

The point estimate (median $8,200) looked fine. The distribution shows a real
chance of going negative — which is exactly the signal a point estimate hides.

## Close the loop: log the call

A decision gate is only trustworthy if its forecasts are calibrated. Record the
forecast and resolve it later against the real outcome so the engine's hit rate
is measurable, not assumed:

```python
from calibration import CalibrationLedger

ledger = CalibrationLedger("forecasts.db")
fid = ledger.record("ending_cash stays >= 0?", 0.61, metric="ending_cash")
# ... reality resolves ...
ledger.resolve(fid, 0)         # it went negative
print(ledger.score())          # Brier / log-loss over everything resolved so far
```

See [`calibration.py`](../v3/calibration.py).

## Positioning guardrail

This is decision-support and scenario analysis, not financial advice. The tool
takes input distributions and returns an output distribution and a boolean — it
never fetches a market price, names a tradable contract, issues a buy/sell, or
touches funds. Keep it on that side of the line.

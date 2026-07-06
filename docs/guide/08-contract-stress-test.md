# Stress-Testing a Contract You Didn't Write

A contract can read perfectly and still be economically broken. The clauses
lawyers check — enforceability, completeness, standard language — are not the
clauses that quietly transfer risk. Those live in the *numbers*: revenue-share
splits, milestone thresholds, sunset triggers, payback schedules, buyout
formulas. Whether they're fair depends on how the underlying business actually
ramps, and a business ramp is a probability distribution, not a sentence.

This guide is the repeatable workflow for turning any revenue-bearing contract
into a SimEngine domain config, simulating the deal 5,000 times, and reading
back which clauses hold up and which fire in futures nobody intended.

It was proven on a real joint-venture negotiation, where a 5,000-run
simulation showed an 18-month $100K ARR sunset clause would fail in
essentially every plausible future — even the 90th-percentile outcome reached
only 54% of the threshold. The clause read fine. The distribution said it was
an exit option disguised as a milestone. The threshold got renegotiated before
signing.

Time budget: 2–4 hours for config plus interpretation. Worth it for any deal
above ~$10K expected value.

## Step 1 — Intake: extract the deal's moving parts

Read the contract once with a highlighter and sort every number and trigger
you find into four buckets. This mapping IS the model design:

| Bucket | Contract language that goes here | Becomes |
|--------|----------------------------------|---------|
| **Uncertain inputs** | demand, close rates, churn, cost rates — anything the contract *assumes* about the business | `parameters` (triangular/normal/lognormal with a written `calibration` note) |
| **Decision levers** | prices, fees, staffing, spend levels either party sets | `controls` (usually `fixed`) |
| **External shocks** | seasonality, market growth, platform/API pricing you don't control | `exogenous` |
| **Clauses with teeth** | sunset/termination thresholds, earn-outs, payback triggers, minimum-performance gates, buyout formulas | `metrics` + `safety.chance_constraints` |

Then write down, per party: what they put in (cash, labor at opportunity
cost), what they take out (share of revenue, fees), and when.

Intake checklist:

- [ ] Every dollar figure in the contract is a parameter, control, or threshold
- [ ] Every date/milestone maps to a step number (`n_steps`, monthly is typical)
- [ ] Every conditional clause ("if X by month N…") has a metric that measures X
- [ ] Both parties' net positions are metrics, not just the venture's total
- [ ] Each uncertain input has a one-line `calibration` note saying where the
      range came from (industry comps, party's own claims, public data)

## Step 2 — Author the config

Start from the shipped JV precedent — copy its shape, not its numbers:

```bash
curl -s http://localhost:8420/api/domain/paint_responsibly_jv.json | python3 -m json.tool | less
```

The structural pattern that makes contract analysis work:

- **Model the ramp, not the endpoint.** `n_steps: 36`, `step_label: "month"`,
  with accumulators for revenue, costs, and each party's cumulative take.
  Milestone clauses are then readable *at their month* from the trajectory
  bands, not just at the end.
- **One metric per clause with teeth.** The JV config's
  `tony_net_vs_opportunity` and `john_payback_on_upfront` exist purely so a
  constraint can ask "what's the probability this party ends up worse off than
  not doing the deal?"
- **Encode the clause as a chance constraint, with the contract text in
  `rationale`.** Example from the precedent:

```json
{
  "metric": "final_arr",
  "condition": "below",
  "threshold": 100000,
  "max_prob": 0.35,
  "rationale": "The 18-month sunset clause triggers at $100K ARR..."
}
```

Validate before running — the validator's errors are precise:

```bash
curl -s -X POST http://localhost:8420/api/validate \
  -H "Content-Type: application/json" -d '{"config": <CONFIG>}'
```

## Step 3 — Simulate and interrogate

Run 5,000 sims (seed it for reproducibility), then work through four
questions in order:

```bash
curl -s -X POST http://localhost:8420/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"config": <CONFIG>, "n_simulations": 5000, "seed": 42}'
```

1. **Do both parties end positive, and how often?** Look at each party's net
   metric: mean, P10, and the probability below zero. A deal that's great at
   the median and ruinous at P10 for one party is a renegotiation, not a
   signature.
2. **Does each milestone clause survive the ramp?** Read the trajectory bands
   at each contract date. A threshold above the P90 band at its trigger month
   is a clause that fires in nearly *all* futures — usually not what either
   party thought they were agreeing to.
3. **Which assumptions carry the deal?** Run sensitivity analysis (the
   Sensitivity button, or `diagnostics.py --sensitivity`). If the deal's
   fairness hinges on one input — say, close rate — that's the number to
   diligence hardest before signing.
4. **What would make it fair?** Use the web UI's **Sweep Control** on the
   contested lever (the fee, the split, the threshold) and read the comparison
   table: at which value does the failing constraint start passing? That value
   is your counter-proposal, with the distribution as the argument.

## Step 4 — Write the two documents

Always produce both; never send the first one:

- **Internal analysis** — includes opportunity-cost framing, negotiation
  leverage, which clauses to push on and the sweep value to push toward.
- **Counterpart-safe summary** — their P10/P50/P90 outcomes, payback period,
  and the shared findings (e.g. "this threshold fails in >90% of futures for
  *both* of us"). Both-sides transparency is what turns "trust me this is
  fair" into "here is what the math says."

If any forecast in the analysis is checkable later ("ARR exceeds $40K by
month 18"), log it in the Predictions ledger (`POST /api/forecast` or the
Track button). A graded track record across deals is the long-term credibility
asset.

## Guardrails

- **This complements attorney review; it never replaces it.** Legal review
  catches language defects; this catches economic ones. Both are required for
  a material deal. (In the precedent case, legal-AI review found language
  issues but missed the economic cliff entirely.)
- **Calibrate inputs from sources you can cite** — industry comps, public
  data, the counterparty's own numbers — and write the source into each
  `calibration` field. The analysis is only as arms-length as its inputs.
- **State what the model omits** (taxes, disputes, key-person risk).
  A stress test that hides its scope is a point estimate with extra steps.
- Output is decision support and scenario analysis — not legal, financial, or
  investment advice, and the documents should say so.

# Model Your Own Decision

You ran a pre-made domain. You read the results. Now you want to point SimEngine at *your* decision: a hire, a price change, a launch, a lease. This is the document the rest of the guide kept promising. By the end, you will have written your own config and run it.

This is the most technical page in the guide, because it shows JSON. Don't let that scare you. You will not write code. You will copy a file that already works and change values inside it, one at a time.

## 1. What a config actually is

A config is a single text file written in JSON. JSON is just a structured way to write text with labels and values — think of it as filling in a form, not writing a program. You write down what you already believe about a decision: the things you know, the things you control, and the things you are unsure about (as ranges).

Two files will save you hours:

- **`v3/domains/_template.json`** — an annotated starter file. Copy it, rename it, and edit the values.
- **`v3/domains/`** — the folder of working examples. Open any one, see how a real decision was modeled, and copy the parts you need.

Every field name this guide explains matches those files exactly. The template also carries a few extra blocks this guide does *not* cover — `description`, `step_label`, `seed`, `_guide`, `calibration`, `fitness`, and `tunable`. They are optional. Ignore them for now; your config runs fine without touching them. Here is the one-line version of each, so nothing in the file looks like a mystery:

| Extra field | What it's for | Safe to ignore? |
|---|---|---|
| `description` | A sentence describing the model. | Yes. |
| `step_label` | What one step is called ("month", "day"). Display only. | Yes. |
| `seed` | A fixed starting point for the random draws, so runs repeat. | Yes. |
| `_guide` | A cheat-sheet note inside the file. Not read by the engine. | Yes. |
| `calibration` | An advanced note on updating a number from real data later. | Yes. |
| `fitness` | A scoring formula used only when you ask the engine to optimize. | Yes. |
| `tunable` | Which dials the optimizer is allowed to turn. | Yes. |

If the `calibration` block mentions "Beta-Binomial conjugate," skip it. That is an advanced feature for updating your numbers once you have real-world data. It does nothing to a plain run.

The fastest way to learn is to copy a file that already runs and change one thing at a time.

## 2. A word about JSON punctuation

JSON has a few rules. Break one and the file won't load. They are invisible to read but easy to follow:

- **Quotes.** Every label and every piece of text needs double quotes: `"name"`, `"Coin Flip"`. Numbers do not: `1000`, `0.5`.
- **Commas.** Every item needs a comma after it — *except the last one in its group*. A trailing comma after the last item is the single most common reason a hand-edited file won't load.
- **Brackets must balance.** Every `{` needs a `}`; every `[` needs a `]`. `{ }` holds a labeled group (like a form). `[ ]` holds a list (an ordered set of items).
- **Colons** separate a label from its value: `"name": "Coin Flip"`.

The safe habit: never type a config from scratch. Open an example, change the values inside the quotes and after the colons, and leave the punctuation alone. When in doubt, validate (Section 7) — it catches a broken file before it wastes your time.

## 3. The smallest thing that runs

Before the full template, here is the smallest config that does something real: flip a fair coin ten times, win a dollar on heads, lose a dollar on tails, and see where you end up.

```json
{
  "name": "Coin Flip",
  "n_simulations": 1000,
  "n_steps": 10,
  "parameters": { "heads": { "distribution": "bernoulli", "params": { "p": 0.5 } } },
  "step_logic": [ { "target": "payout", "expr": "1 if heads > 0.5 else -1" } ],
  "accumulators": { "bankroll": "bankroll + payout" },
  "metrics": { "final_bankroll": { "expr": "bankroll", "format": "number" } },
  "initial_state": { "bankroll": 0 }
}
```

Read it top to bottom. Every field has one job:

| Field | What it does |
|---|---|
| `name` | A label for this simulation. Shows up in the UI. |
| `n_simulations` | How many times to run the whole story. Here, 1,000 separate ten-flip games. More runs, smoother results. |
| `n_steps` | How many steps each run takes. Here, 10 coin flips. |
| `parameters` | The uncertain inputs. Here, one: `heads`, a coin flip that comes up 1 (heads) with probability `p: 0.5`, otherwise 0. |
| `step_logic` | What happens each step. Here: set `payout` to +1 if the flip was heads, else -1. |
| `accumulators` | Running totals carried from step to step. Here: add each `payout` to `bankroll`. |
| `initial_state` | The starting value for each accumulator. `bankroll` starts at 0. |
| `metrics` | The final numbers you read. Each needs a `format` (here `"number"`); leave it out and it just defaults to `"number"`. |

Run this 1,000 times and you do not get one answer — you get a spread. Picture the thousand games landing in a pile: most end near zero, a fair number end a dollar or two up or down, and a rare few swing to plus or minus six. That pile *is* the result. SimEngine shows you the range of what could happen, not a single guess.

That is a complete, runnable model. Everything else in this document adds richness to these same seven ideas.

## 4. The one move that matters most: turn "I'm not sure" into a range

This is the skill that makes the whole engine useful. You rarely know an exact number. You usually know a *range* with a likely middle. SimEngine has a distribution built for exactly that thought: the **triangular**.

A distribution is just a description of an uncertain number — what values it can take and which are more likely. The triangular takes three numbers, and the mapping from plain English is direct:

> "I think it's somewhere **between 10% and 50%**, but **usually around 25%**."

becomes:

```json
{ "distribution": "triangular", "params": { "low": 0.10, "mode": 0.25, "high": 0.50 } }
```

- `low` — the worst plausible case.
- `mode` — the most likely value (the peak).
- `high` — the best plausible case.

If you can finish the sentence "between X and Y, usually Z," you can model it. **Triangular is the workhorse.** Reach for it first whenever a number comes from your judgment rather than hard data.

The other distributions, and the one situation each is for:

| Distribution | Params | Use it when... |
|---|---|---|
| `fixed` | `{value}` | The number is certain. A known price, a set budget. |
| `triangular` | `{low, mode, high}` | You have a range with a likely middle. **Your default.** |
| `uniform` | `{low, high}` | Anywhere in a range is equally likely; you have no "usual." |
| `normal` | `{mean, std, min?, max?}` | Values cluster symmetrically around an average (a bell curve). `mean` is the center, `std` is how far they typically spread from it. |
| `lognormal` | `{median, spread, min?, max?}` | Values can't go below zero and have a long upper tail — costs, durations, demand spikes. |
| `bernoulli` | `{p}` | A yes/no event with probability `p`. Did the deal close? Did the part fail? |
| `poisson` | `{lambda}` | A count of independent events in a period — calls per hour, defects per batch. `lambda` is the average. |

The `min?` and `max?` mark optional clamps: hard floors or ceilings on a distribution that could otherwise wander past what is physically possible. Leave them out if you don't need them.

For `lognormal`, `spread` controls how wide the upper tail gets: 0.3 is modest, 0.6 is wide. If that's not intuitive, that's the sign to use triangular instead.

Two more distributions exist in the engine — `student_t` and `correlated_normal` — and you may see them named in the template's `_guide` note or in an advanced example. They are for specialized cases. You don't need them to model a real decision. The seven in the table above cover nearly everything.

Start with triangular for nearly everything. Only switch when you have a specific reason.

## 5. The three kinds of input

Every uncertain input you write goes in one of three buckets. All three use the same `{distribution, params}` shape — the bucket only describes the *role* the number plays in your decision.

- **`parameters`** — uncertain unknowns about the world. Things you don't control and don't know for sure, but could learn from data. *Example: your conversion rate.*
  ```json
  "conversion_rate": { "distribution": "triangular", "params": { "low": 0.10, "mode": 0.25, "high": 0.50 } }
  ```
- **`controls`** — your decisions. The dials you can turn. *Example: how much you spend per month.*
  ```json
  "monthly_budget": { "distribution": "fixed", "params": { "value": 2000 } }
  ```
- **`exogenous`** — outside factors. Things that affect the outcome but that nobody at the table controls — weather, market demand, a competitor's move. *Example: incoming demand.*
  ```json
  "demand": { "distribution": "triangular", "params": { "low": 5, "mode": 20, "high": 50 } }
  ```

Why bother splitting them? Because the split tells SimEngine which numbers are yours to choose. Controls are the dials. When you later ask the engine to *optimize* — to search for a better decision — it only turns the control knobs, because those are the only things you can actually change in real life. Parameters and exogenous factors stay fixed as the world you're playing against.

## 6. Building the story

Three sections turn your inputs into answers. The examples below come straight from `v3/domains/_template.json`.

### step_logic — what happens each step

`step_logic` is a list. Each entry has a `target` (a name for the result) and a formula. Almost always the formula is an `expr` — a calculation written as text. Entries run top to bottom, every step, and can use the results of earlier entries.

```json
"step_logic": [
  { "target": "sales",   "expr": "binomial(round(demand), conversion_rate)" },
  { "target": "revenue", "expr": "sales * 100" },
  { "target": "costs",   "expr": "monthly_budget" }
]
```

In plain words: each step, some number of customers (`demand`) show up; each converts with probability `conversion_rate`, giving a count of `sales`; revenue is `sales * 100`; costs are this month's `monthly_budget`.

A few things in that example need a plain-language gloss:

- `binomial(n, p)` — flip a weighted coin `n` times, each with success chance `p`, and count the successes. `binomial(round(demand), conversion_rate)`: out of (roughly) `demand` visitors, how many convert at rate `conversion_rate`.
- `round(demand)` — round to a whole number. You can't have 19.4 visitors.
- `_step` — a **built-in** you don't define yourself. It's the current step number, starting at 1 on the first step. Use it for anything that changes over time. Example: `base_demand * (1.05 ** _step)` grows demand 5% per step. Because `_step` is built in, using it does *not* count as "referencing a name you never defined" (see Section 8).

`step_logic` entries can also take a `sample` instead of an `expr` — a fresh random draw, written the same way as a parameter:

```json
{ "target": "shock", "sample": { "distribution": "normal", "params": { "mean": 0, "std": 1 } } }
```

Most models never need this; use `expr` and define your randomness up in `parameters` or `exogenous`.

Expressions can use ordinary math (`+ - * /`) and a set of named functions. You only need three for typical models:

- `round(x)` — round to a whole number.
- `clamp(val, lo, hi)` — keep a number inside limits. `clamp(sales, 0, 1000)` never goes below 0 or above 1,000.
- `binomial(n, p)` — count successes out of `n` tries (above).

The full list, for when you need it — ignore everything past the first three until you do:

```
min, max, abs, round, sum, len, int, float,
sqrt, log, exp, ceil, floor, pow,
random(), gauss(mu, sigma), binomial(n, p), clamp(val, lo, hi)
```

(`gauss(mu, sigma)` draws one bell-curve number, where `mu` is the center and `sigma` the spread; `random()` draws a number between 0 and 1.)

Conditions work too, in the form `A if condition else B`:

```json
{ "target": "payout", "expr": "100 if profit > 0 else 0" }
```

### accumulators + initial_state — running totals

An accumulator is a number that carries across steps and updates each one. `initial_state` sets where each accumulator starts.

```json
"initial_state": { "cumulative_revenue": 0, "cumulative_costs": 0 },
"accumulators": {
  "cumulative_revenue": "cumulative_revenue + revenue",
  "cumulative_costs":   "cumulative_costs + costs",
  "net_position":       "cumulative_revenue - cumulative_costs"
}
```

Each step, `cumulative_revenue` grows by that step's `revenue`, `cumulative_costs` grows by its `costs`, and `net_position` is the gap between them — your running profit.

Always give each accumulator a starting value in `initial_state`. If you forget, the engine doesn't error — it quietly starts that accumulator at 0. That's a convenience, but it's also a trap: a silent 0 can hide a real mistake. Set the start value yourself so you know it's right (in the example, `net_position` is derived from the other two, so it doesn't need its own line).

### metrics — the answers you read

`metrics` are the final numbers SimEngine reports after all steps finish. Each has an `expr` and, optionally, a `format` that controls how it displays.

```json
"metrics": {
  "total_revenue": { "expr": "cumulative_revenue", "format": "dollar" },
  "total_profit":  { "expr": "net_position",       "format": "dollar" }
}
```

`format` is one of `"dollar"`, `"percent"`, or `"number"`. It is optional and defaults to `"number"` if you leave it out — but set it anyway, so dollars read as dollars and percentages read as percentages. Because you ran thousands of simulations, each metric comes back as a spread (a median, a worst case, a best case), not a single figure. That is what the Reading the Results document taught you to interpret.

## 7. Adding your risk lines (optional, recommended)

A model that only reports the average hides the downside. The `safety` section names the bad outcomes you want to watch and how much of them you'll tolerate. It is optional — your config runs fine without it — but it's worth adding once your model works.

```json
"safety": {
  "chance_constraints": [
    { "metric": "total_profit", "condition": "below", "threshold": 0, "max_prob": 0.20,
      "rationale": "No more than 20% chance of ending in the red" }
  ],
  "cvar_constraints": [
    { "metric": "net_position", "alpha": 0.10, "min_cvar": -10000,
      "rationale": "Worst 10% must not exceed $10k loss" }
  ]
}
```

In plain language:

- **`chance_constraint`** — "How often is this allowed to go wrong?" The example says: `total_profit` going **below** the `threshold` of 0 must happen in at most **20%** of runs (`max_prob: 0.20`). It caps the *odds* of a bad outcome.
- **`cvar_constraint`** — "When it goes wrong, how bad is the bad?" CVaR looks only at the worst slice of runs — here the worst **10%** (`alpha: 0.10`) — and requires their average not fall below `min_cvar` of -$10,000. It caps the *severity* of the tail, not just its frequency.

The `rationale` is a plain note to yourself explaining the limit. Write it for the version of you who reopens this file in six months.

## 8. Run it

Start with the two paths that need no terminal:

1. **Drop it in the folder.** Save your file in `v3/domains/` (for example `v3/domains/my_launch.json`) and refresh the web UI. It appears in the domain list, ready to run.
2. **Paste it into the UI.** Paste the JSON straight into the web interface and run.

**For the technically inclined (optional).** You can also work from the terminal or the API:

- Validate without running: `POST /api/validate`.
- Run a config through the API: `POST /api/simulate` with a body of `{"config": { ... }}`.
- Validate and run from the command line:
  ```bash
  python3 kernel.py domains/yourfile.json --seed 42
  ```

If you're not a programmer, skip this block — the folder and paste paths do everything you need.

**Validate before you trust a run.** Validation catches structural problems before they waste a simulation. It returns a plain list of problems, naming what's wrong — a missing field, an unknown distribution, a formula that produces a non-number. Fix what it names, validate again, and only then read the numbers.

The `--seed 42` makes the run repeatable: the same seed gives the same random draws every time, so you can change one input and trust that any difference came from your change, not from luck.

## 9. Common mistakes

Almost every first config trips on one of these:

- **A broken comma or bracket.** A trailing comma after the last item, or an unbalanced `{ }` or `[ ]`, stops the file from loading. See Section 2. Editing values inside an example (not typing from scratch) avoids most of these.
- **Referencing a name you never defined.** An `expr` uses `conversion_rate`, but no parameter, control, exogenous, or earlier `target` by that name exists. Every name in a formula has to come from somewhere — except the built-in `_step`, which is always available.
- **Spelling a distribution wrong, or inventing one.** Use the exact names from the table in Section 4. (There is no `beta` distribution, for instance.)
- **Wrong params for the distribution.** `triangular` needs `low`, `mode`, `high`; `normal` needs `mean` and `std`. Mismatched keys fail validation.
- **Order in `step_logic`.** An entry can only use results defined above it. If `revenue` uses `sales`, `sales` must come first.

Two things that *won't* error but can still bite you: a metric with no `format` (it silently becomes `"number"`), and an accumulator missing from `initial_state` (it silently starts at 0). Neither stops the run, so set both yourself rather than trusting the default.

When in doubt, validate. The error list points at the exact problem.

## 10. One honest line

SimEngine does the arithmetic perfectly. It cannot check whether your ranges are right. A model built on careless guesses produces confident-looking nonsense. The numbers are only as good as the ranges you choose — which is exactly why it's worth slowing down to choose them well.

# Reading the Results

You ran a simulation. SimEngine handed you a screen full of numbers, bands, and a pass/fail flag. This guide makes you fluent at reading all of it.

We will use one real result the whole way through: the **Freelance Developer/Designer — Income Viability** scenario, run 5,000 times. The decision behind it is simple: *Can I go full-time freelance and sustain a livable income?*

In SimEngine, one decision scenario like this is called a **domain** — the freelancer question is one domain; an indie software business is another. You set up a domain once, then run it.

In a hurry? There is a full cheat sheet at the end of this guide — every statistic in one table. Skip to it anytime. By the end of this guide, you will be able to look at any SimEngine result and say what it means for your decision.

## First, what a result actually is

SimEngine runs a **Monte Carlo simulation** — a fancy name for a simple idea. Instead of giving you one forecast, it plays out the same decision thousands of times. Each time, it rolls fresh values for the unknowns: how many clients you land, what they pay, how often you are between jobs. Each run is one possible future. Five thousand runs is five thousand futures.

Where do those rolled values come from? Not thin air. You (or the domain you started from) set a plausible range for each unknown — for example, "freelance developers bill somewhere between $75 and $200 an hour, usually around $120." SimEngine rolls inside the ranges you gave it. The futures are only as good as those assumptions, which is why every honest result is paired with the inputs that produced it.

So every output is not a single number. It is a *pile* of 5,000 numbers. The job of reading results is learning to describe that pile: where its center is, how spread out it is, and how bad the bad cases get.

> **One note on "seed 42."** You may see a seed number attached to a run. A seed just makes the random rolls repeatable — run it again with the same seed and you get these exact numbers. It is for reproducibility, nothing more. Ignore it if you like.

## The median — the most likely middle

The first number SimEngine shows for each output is the **median**. The median is the middle of the pile: line up all 5,000 futures from worst to best, and the median is the one standing dead center, at position 2,500. Half the futures came out better, half came out worse.

For the freelancer:

- **Annual gross income: median $107,317** — total billings before costs and taxes.
- **Annual net income: median $27,298** — what is left after costs and taxes.

Read that gap out loud. The most likely gross is six figures. The most likely take-home is about a quarter of that. If you only looked at gross, you would badly misjudge this decision.

> **Why median, not average (mean)?** The median is not skewed by a few extreme runs. If one future has a freak $500k year, it drags the *average* up but leaves the *median* — the true middle — untouched. For decisions, the middle is usually the honest number.

## The 80% range — why two numbers beat one

A single number hides everything that matters. So SimEngine reports a range alongside it: the **p10** and the **p90**.

Picture all 5,000 futures lined up worst to best again.

- **p10** ("10th percentile") is the future standing at position 500 — only the worst 10% did worse. A low bar.
- **p90** ("90th percentile") is the future at position 4,500 — only the best 10% did better. A high bar.

The span from p10 to p90 is the **80% range**: 80% of all simulated futures landed inside it. It is the honest answer to "what should I actually expect?"

Here is the freelancer, center and range together:

| Output | What it means | Median (middle) | 80% range (p10 to p90) |
|---|---|---|---|
| Annual gross income | Total billings before costs/taxes | $107,317 | $78,065 to $137,738 |
| Annual net income | Take-home after costs/taxes | $27,298 | $2,521 to $53,064 |
| Ending savings | Cash in the bank at year-end | $47,298 | $22,521 to $73,064 |
| Utilization rate | Share of available hours you actually bill | 49% | — |
| Effective hourly | Take-home divided by *every* hour billed | $33 | $4 to $53 |

Two of those rows need a plain-English word before they make sense:

- **Utilization rate** is the percent of your available working hours you actually bill a client for. The freelancer can bill up to 140 hours a month; at 49% utilization, fewer than half those hours turn into paid work. The rest goes to finding clients, admin, and gaps between projects.
- **Effective hourly** is your real wage: take-home pay divided by *every* hour you billed. It is not your rate card. A $120/hr rate becomes a $33/hr median once costs, taxes, and unpaid stretches are folded in.

> **Where does $47,298 come from?** Ending savings is roughly net income plus the **$20,000 starting cushion** the freelancer began the year with ($27,298 + $20,000 ≈ $47,298). That is the emergency fund in the bank before going full-time.

One average would have told you "net income around $27k." The range tells you the truth: net income could be a comfortable **$53,064** or a white-knuckle **$2,521**, depending on how the year breaks.

## What a wide range is telling you

The *width* of the range is a signal all by itself. A narrow range means the outcome is predictable. A wide range means the income is **lumpy** — good years and lean years both sit well inside normal, and small swings in your luck move the result hard.

Look at the freelancer's net income: **$2,521 to $53,064**. That is roughly a 20x spread between the bottom and top of the likely band. Translation: plan for the lean years, not just the good ones.

The widest signal of all is **effective hourly: median $33, but an 80% range of $4 to $53**. In the worst tenth of futures, you are effectively working for about **$4 an hour** — below minimum wage. That is not a rounding error. It is a real, roughly 1-in-10 outcome that a single average ("$33/hr") would have buried completely. The pull runs downward here: the average effective hourly ($30) sits *below* the median ($33), because the worst cases drag it down. That is the lumpiness showing up in the math.

A wide range is not automatically bad. It is information. It tells you where to build a cushion.

## The histogram — the shape of the pile

The range gives you two edges. The **histogram** shows you the whole shape in between.

A histogram sorts all 5,000 outcomes into buckets and draws a bar for how many futures landed in each bucket. Tall bars are common outcomes; short bars are rare ones. A rough sketch of the freelancer's net-income histogram:

```
  count
   ^
   |        ███
   |        ███ ███
   |    ███ ███ ███
   |    ███ ███ ███ ███
   |    ███ ███ ███ ███ ██   ▄▄  ▁▁
   +----+---+---+---+---+----+---+--->  net income
       $2.5k         $27k        $53k
       (p10)      (median)       (p90)
```

Reading the shape tells you things a range cannot:

- **Where the outcomes clump.** One tall peak means most futures cluster in one place. Two separate peaks would mean two different stories (e.g., "landed the big client" vs. "didn't").
- **Which way it leans.** Here the bars trail off gently to the right — a few good years stretch the top end. That right lean is mild for the freelancer (the mean, $27,520, sits only just above the median, $27,298), but it is real, and it is exactly why the median sits below the best outcomes.

Most years are modest, a few are good, and the good ones nudge the average up without making themselves likely.

## Trajectory bands — how the range grows over time

Everything above describes the *final* outcome. SimEngine also shows you the path. **Trajectory bands** plot three lines across every month of the simulation:

- the **p50** (median) line — the typical path,
- the **p10** line — the pessimistic path,
- the **p90** line — the optimistic path.

A rough sketch:

```
 value
   ^                              ___---  p90 (optimistic)
   |                  ___------```
   |        ___------``________------  p50 (median)
   |   ----``__________
   |              ```------___________  p10 (pessimistic)
   +-------------------------------------> month
   1                                  12
```

Early on, the three lines sit close together — little has happened yet, so futures have not diverged. As the months pass, the p10 and p90 lines fan apart. That widening cone is uncertainty compounding: each month of unknowns stacks on the last. The band shows you not just *that* the outcome is uncertain, but *when* the uncertainty opens up — and how early a bad path starts to separate from a good one.

## Risk language: chance constraints and CVaR

A center and a range describe outcomes. The next two ideas describe **risk** — and this is where SimEngine earns its keep, because it checks risk against limits *you* set and reports a plain **PASS** or **FAIL**.

To show what both look like, we will bring in a second domain partway through: an **Indie SaaS** business (a small subscription software startup), which SimEngine ran the same way. The freelancer passes its safety checks. The SaaS business fails — and seeing both is the fastest way to learn what the checks mean.

### Chance constraints — "how often does the bad thing happen?"

A **chance constraint** is a safety rule that caps how often a bad outcome is allowed to happen. You name the bad thing and the most you will tolerate — say, "no more than a 10% chance of running out of savings." SimEngine counts how many of the 5,000 futures hit that bad outcome and checks the count against your limit.

The freelancer set this safety rule:

> Chance of ending savings below $0 = **0.66%** — limit was 10% — **PASS**

In plain words: across 5,000 simulated years, fewer than 1% ended with savings underwater. Your limit said you would tolerate up to 10%. You are well under it. Pass.

Now the Indie SaaS business, running the same kind of check, fails hard:

> Chance of ending cash below $0 = **100%** — limit was 15% — **FAIL**

Read that. *Every single one* of the 5,000 SaaS futures ended out of cash. Not the risky tenth — all of them. A spreadsheet that said "monthly recurring revenue about $2,088 by month 24" would have looked fine and hidden the fact that you go broke getting there. (Monthly recurring revenue, or MRR, is the predictable subscription income a business collects each month.) That gap — between a tidy single number and the full range of futures — is the entire reason SimEngine exists.

The two results side by side:

| Check | Freelancer | Indie SaaS |
|---|---|---|
| Chance of running out of money | 0.66% | 100% |
| Your stated limit | 10% | 15% |
| Verdict | PASS | FAIL |

### CVaR — "how bad is bad, on average?"

A chance constraint counts *how often* the bad thing happens. **CVaR** measures *how deep* it goes when it does.

CVaR — short for Conditional Value at Risk — has a one-line definition: **the average of the worst outcomes.** Take the worst slice of futures (here, the worst 10%) and average just those. It answers, "when things go badly, how badly, typically?" One disaster run can be a fluke; the average of the whole worst tenth is a number you can plan around.

The freelancer's CVaR rule:

> CVaR of the worst 10% of net income = **-$6,206** — limit was -$20,000 — **PASS**

> **Wait — how is that negative?** Earlier we said the p10 net income was a *positive* $2,521. CVaR can still be negative because it averages *everything below* p10, including the rare disaster years far worse than $2,521. The p10 is one point near the edge; CVaR is the average of the whole bad tail behind it. So the worst-tenth average ($-6,206) lands below the p10 figure, and below zero.

Meaning: even averaging the ten-percent-worst years, net income lands at about **-$6,206**. Unpleasant — a small loss — but nowhere near the **-$20,000** floor you said you could survive. Pass.

By contrast, the SaaS CVaR:

> CVaR of the worst 10% of ending cash = **-$40,342** — limit was -$15,000 — **FAIL**

The worst-tenth average is **-$40,342**, far below the -$15,000 you could stomach. The bad cases here are not just frequent — they are deep.

### Putting safety together

A domain can set several safety rules. **All of them must pass** for the overall verdict to be PASS.

- **Freelancer:** every check passed → **all_passed = true.** The decision ("go full-time?") looks viable — with eyes open about the lean months.
- **Indie SaaS:** chance constraints and CVaR both failed → **all_passed = false.** The business bleeds cash in every future.

## The narrative and the fitness score

Two more pieces round out a result.

The **narrative** is a short, plain-English paragraph SimEngine writes automatically from the numbers. It is a sanity check and a starting point — useful for pasting into a memo — but it never replaces reading the range and the safety flags yourself.

The **fitness score** is a single number that grades the whole result against the domain's goals, with safety violations dragging it down. Its only real use is comparison: when you ask SimEngine to *tune* a domain — try different settings automatically to find a better configuration — the fitness score is how it tells a better setup from a worse one. On its own, one fitness number means little. Across two runs, the higher one is the better outcome by the domain's own goals. Treat it as a scoreboard, not a verdict — the range and the safety checks are where you actually read the decision.

## The cheat sheet

Every statistic, what it means in human words, and what to do with it:

| Statistic | Plain English | What to do with it |
|---|---|---|
| **median (p50)** | The middle outcome; half of futures are better, half worse | Use as your single best guess — not the average, which extremes distort |
| **mean** | The straight average of all futures | Compare to the median; a gap means a lopsided result with a tail one way |
| **p10** | Only the worst 10% of futures did worse | Treat as your realistic downside — plan a cushion for it |
| **p90** | Only the best 10% of futures did better | Treat as upside, not a plan |
| **80% range (p10–p90)** | Where 80% of futures land | The honest "what to expect"; wide = lumpy, narrow = predictable |
| **std (standard deviation)** | The typical distance of a single future from the average — a one-number gauge of spread | Bigger std = more uncertain. Net income at $2.5k–$53k has a large std; a tight, predictable output has a small one |
| **histogram** | The shape of all 5,000 outcomes | Spot clumps, lean, and whether there are two different stories |
| **trajectory bands** | How the p10/p50/p90 paths widen over time | See when uncertainty opens up and when a bad path separates |
| **chance constraint** | A cap on how often a bad outcome may happen | Read the PASS/FAIL — is the bad thing rare enough for you? |
| **CVaR** | The average of the worst X% of outcomes | Read how *deep* the bad cases go, not just how often |
| **all_passed** | Did every safety rule pass? | One FAIL flips it to false — your hard stop |
| **narrative** | Auto-written plain-English summary | A starting point; never a substitute for reading the numbers |
| **fitness score** | One graded number for the whole result | Compare across runs; higher is better by the domain's goals |

## Reading the freelancer result in one breath

Put it all together and the whole decision fits in a paragraph:

> Gross income most likely lands near **$107,317**, but take-home is far lower and lumpy — net income most likely **$27,298**, and anywhere from **$2,521 to $53,064** in 8 out of 10 years. In the worst tenth of futures you are effectively earning about **$4 an hour**. Even so, savings almost never go negative (**0.66%** chance, well under your 10% limit), and the worst-tenth average net income (**-$6,206**) stays well above your -$20,000 floor. Every safety rule passed. **Verdict: viable — go in expecting lean stretches and keep a cushion.**

That is reading the results. You are no longer looking at a wall of numbers. You are looking at a decision.

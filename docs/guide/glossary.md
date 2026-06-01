# Glossary

This page defines every term you will meet in the SimEngine guide. Each entry gives you a plain-language definition and a short "why you care." Skip around as needed. Terms are grouped into three sections: **Core Ideas** (what the engine does), **Reading Results** (how to make sense of the output), and **Advanced** (optimization, learning from data, and connecting tools).

If you remember one thing: SimEngine is a calculator for uncertainty. You describe a decision and its unknowns; it plays out thousands of possible futures and tells you the full range of what could happen, how likely each is, and where the risks are.

> **The two running examples.** Throughout this glossary we lean on two real reports. The first is a **SaaS business** — short for software-as-a-service, a company that sells software by subscription — that looked risky. The second is a **freelance career** that looked safe. Both ran 5,000 simulations over a 24-month (two-year) horizon. When you see scattered numbers below, they come from these two.

---

## Core Ideas

### Monte Carlo simulation
A method that answers "what could happen?" by trying a decision thousands of times, each time with slightly different guesses for the things you don't know for sure, then collecting all the outcomes. The name comes from the casino town — the method uses chance on purpose.
**Why you care:** A spreadsheet gives you one answer. Monte Carlo gives you the full spread of answers, so you see the good cases, the bad cases, and how often each shows up.

### Simulation run
One complete play-through of your decision from start to finish, using one specific set of guesses for the unknowns. Thousands of runs together make up a simulation. Our two example reports each used 5,000 runs.
**Why you care:** No single run is "the answer." The answer lives in what the whole pile of runs looks like together.

### Distribution
The shape of all the possible values a number can take, and how likely each one is. For example, your monthly revenue might most likely land near $2,000, but could plausibly run anywhere from roughly $1,650 to $2,550.
**Why you care:** Real unknowns are not single numbers. Describing them as a distribution is how you tell the engine "I'm not sure, but it's probably around here."

### Probability
A number between 0% and 100% saying how likely something is. 0% means it never happens; 100% means it always happens.
**Why you care:** SimEngine reports risk as probabilities you can act on — like "100% chance you run out of cash" versus "0.66% chance your savings go negative." Those two sentences lead to very different decisions.

### Domain config
A single JSON file that describes one decision: its unknowns, its rules, and what you want to measure. JSON is just a structured text file you fill in like a form — no programming required. "Domain" just means "the thing you're modeling" — a SaaS (subscription software) business, a freelance career, a project.
**Why you care:** This file is the whole input. You fill it in once and the engine handles the rest — nothing to build from source code, nothing to install.

### Parameter / Control / Exogenous
The three kinds of inputs in a config.
- **Parameter** — an uncertain unknown you can't directly set, like your customer churn rate (the rate at which customers cancel and leave).
- **Control** — a decision you get to make, like your price or your marketing budget.
- **Exogenous** — an outside factor beyond your control, like the broader market or inflation.

**Why you care:** Sorting inputs this way is what lets the engine later tell you which dials are yours to turn (controls) versus which you just have to plan around (parameters and exogenous factors).

### Step logic
The rules for what happens in each time step of the simulation — usually one month. For a SaaS business, a step might be: add new customers, lose some to churn (customers who cancel), collect revenue, pay costs.
**Why you care:** This is the engine of your model. It is how a starting situation turns into a 24-month story instead of a single guess.

### Accumulator
A running total that builds up across the time steps, like total revenue collected so far or cash in the bank.
**Why you care:** Accumulators are how the simulation remembers the past. They let you track things like "did we ever run out of money along the way," not just the final score.

### Metric
A final number the engine reports at the end of a run, like final monthly revenue, ending cash, or months to profit.
**Why you care:** Metrics are the answers to your real questions. In our SaaS example, the key metrics were final MRR — monthly recurring revenue, the predictable income a subscription business collects each month — with a median of $2,088, and ending cash with a median of -$33,205. (A negative number means you've spent more than you have and gone into debt.)

### Trajectory
The path a number takes over time, step by step, instead of just its final value. SimEngine reports trajectory bands — the typical low, middle, and high path month by month.
**Why you care:** Two businesses can end at the same place by very different routes. The trajectory shows you whether you bleed cash early, recover late, or stay steady throughout.

---

## Reading Results

### Median vs Mean
Two ways to describe the "typical" outcome.
- **Median** — the middle value: half the outcomes are below it, half above. In our freelance example, median net income was $27,298.
- **Mean** — the plain average: add everything up and divide by the count.

**Why you care:** The median is harder to fool. If one billionaire walks into a room of ten people, the average income skyrockets but the median barely moves. A few extreme outcomes can drag the mean far from where most results actually land, while the median stays put. SimEngine reports both.

### Percentile
A cutoff that tells you what fraction of outcomes fall below a given value. The 90th percentile is the value that 90% of outcomes come in under.
**Why you care:** Percentiles turn a messy pile of results into clear statements like "9 times out of 10 you'll do better than this number."

### p10 / p50 / p90
Shorthand for three specific percentiles: p10 (the low end — only 10% of outcomes are worse), p50 (the median, the middle), and p90 (the high end — only 10% of outcomes are better). Together they sketch the realistic range.
**Why you care:** This is the heart of every SimEngine report. In the freelance example, annual net income ran from $2,521 (p10) to $27,298 (median) to $53,064 (p90) — a wide, lumpy spread you would never see from a single forecast.

### Range (80% range)
The span between the low and high ends of the likely outcomes. SimEngine's "80% range" runs from p10 to p90, meaning 8 out of 10 outcomes land inside it.
**Why you care:** The range is the honest version of an estimate. "Final MRR around $2,088" hides the truth; the SaaS example's full 80% range — $1,653 (p10) to $2,552 (p90) — tells you how much wiggle room you're really dealing with.

### Standard deviation
A measure of how spread out the outcomes are. A small standard deviation means results cluster tightly together; a large one means they're all over the map.
**Why you care:** It's a quick gauge of how uncertain a result is. Two metrics with the same median can carry very different risk, and the spread is where that shows up.

### CVaR (Conditional Value at Risk)
The average outcome in the worst slice of cases. "CVaR of the worst 10%" means: line up the bottom 10% of results and average them. It answers "when things go badly, how bad is bad on average?"
**Why you care:** A single worst case can be a fluke. CVaR captures the typical disaster, which is what you actually need to survive. In the SaaS example, the worst-10% ending cash averaged -$40,342 — well past the -$15,000 limit the config set, and deep into debt.

---

## Safety and Scoring

### Safety constraint
A rule you set defining an unacceptable outcome, which the engine checks every result against. SimEngine reports a plain pass or fail. There are two kinds: chance constraints and CVaR constraints (both below).
**Why you care:** This is your line in the sand. The SaaS example failed its safety check on every count; the freelance example passed all three. That single pass/fail often is the decision.

### Chance constraint
A safety rule about how often a bad thing is allowed to happen: "the probability of [metric] crossing [threshold] must not exceed [X%]." Example: "chance of ending cash below $0 must stay under 15%."
**Why you care:** It puts a hard ceiling on a specific risk. The SaaS example set that 15% ceiling and blew through it — the real probability was 100%.

### CVaR constraint
A safety rule about the depth of the bad cases rather than how often they happen: "the average of the worst X% of outcomes must be at least [Y]." It guards against catastrophic worst-case outcomes, not just frequent small misses.
**Why you care:** Some risks are rare but ruinous. A CVaR constraint makes sure that even when you lose, you don't lose more than you can afford.

### Fitness
A single score that rates how good an outcome is overall, combining the things you care about into one number. You define what "good" means in the config.
**Why you care:** It collapses many metrics into one scoreboard, which is what lets the optimizer (see the Optimization section below) compare two strategies and tell which is better.

---

## Advanced: Optimization

### Optimizer / Genetic algorithm
A tool that automatically searches for the best settings of your controls (your decisions). A genetic algorithm does this by imitating natural selection: it tries many combinations, keeps the ones that score highest on fitness, mixes and tweaks them, and repeats over many generations.
**Why you care:** Instead of guessing prices and budgets by hand, you let the engine hunt for the combination that scores best — while still respecting your safety constraints.

### Tunable
The specific controls you give the optimizer permission to adjust, along with the range it's allowed to try.
**Why you care:** It keeps the optimizer inside reality. You decide which dials it may turn and how far, so it can't propose a price of $0 or a budget you don't have.

---

## Advanced: Learning From Data

### Prior
Your starting belief about an unknown, before you've seen fresh data — usually expressed as a distribution. For example, "I think our trial-to-paid conversion is around 5%, but I'm not sure."
**Why you care:** It's how you put your honest, current best guess into the model — including how unsure you are.

### Posterior
Your updated belief after combining your prior with real data. It's the prior, corrected by what actually happened.
**Why you care:** This is the payoff of measuring. As real numbers come in, your model stops running on guesses and starts running on evidence.

### Bayesian updating
The method for turning a prior into a posterior as data arrives. ("Bayesian" just refers to this update rule.) Each new batch of real results tightens your estimate.
**Why you care:** Your first config is built on assumptions. Bayesian updating is how it gets sharper and more trustworthy every month you operate.

### Conjugate prior
A convenient pairing of belief-shape and data-type that makes the Bayesian update fast and exact — no heavy computation. SimEngine uses three: Beta-Binomial (for rates like conversion), Gamma-Poisson (for counts like signups), and Normal-Normal (for averages like deal size).
**Why you care:** You don't need to know the math. You just need to know these three pairings cover most real inputs, and the update happens instantly.

### Calibration
Whether your stated probabilities match reality over time. If you say "70% likely" about many things, a well-calibrated forecaster is right about 70% of those times.
**Why you care:** A forecast you can't check is just an opinion. Calibration is the proof that the engine's probabilities mean what they say.

### Brier score
A grade for how good your probability forecasts were, scored after the real outcomes are known — so you can tell whether to trust the next forecast or take it with salt. The scale: 0.0 is perfect, 0.25 is what you'd get by always guessing a coin-flip 50/50, and 1.0 is the worst possible. Lower is better.
**Why you care:** It's the scoreboard for calibration. A track record of low Brier scores is what lets you trust the next forecast instead of taking it on faith.

---

## Advanced: Connecting Tools

### Prediction market
A market where people buy and sell contracts that pay out based on whether a future event happens, so the live price acts like a crowd's probability estimate. A contract trading at 30 cents reflects roughly a 30% chance (these prices are normalized into implied probabilities, so they aren't exactly a probability, but they're close).
**Why you care:** SimEngine can pull a live price from Polymarket — a public prediction-market website — if you choose to turn that feature on, and turn it into a starting prior for an unknown: a crowd-sourced best guess you then refine with your own data. The price is only an input to your simulation, never a trade signal.

### MCP (Model Context Protocol)
A way for AI assistants like ChatGPT or Claude to use SimEngine on your behalf. SimEngine ships with nine of its functions exposed this way — run a simulation, optimize your controls, check whether you've run enough simulations to trust the result, and more.
**Why you care:** It means you can ask an AI assistant a real decision question and have it run a proper uncertainty analysis, rather than guess. One of those tools weighs the spread of possible outcomes and answers "proceed" or "escalate" — judging the risk in the result, not the AI's confidence in its own words.

---

A closing note on honesty: SimEngine is decision-support, not a crystal ball and not financial advice. It issues no buy or sell signals. Its job is to show you the full range of what could happen so you decide with your eyes open. The numbers are only as good as the config you give it — which is exactly why calibration and Bayesian updating matter: they keep the model honest against reality over time.

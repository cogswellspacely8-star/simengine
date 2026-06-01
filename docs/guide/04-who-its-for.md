# Who It Is For (and Why)

SimEngine is a calculator for uncertainty. You describe a decision and the things you don't know yet in a short text file, run one command, and it plays out thousands of possible futures, then reports the full range of what could happen, how likely each outcome is, and where the risk hides.

A regular calculator answers "what is 7 times 8." SimEngine answers "if I'm not sure about five different things, what's the range of ways this could turn out, and how often does it go badly." Most planning tools give you one number. The real world gives you a spread. SimEngine shows you the spread.

This page is about who actually needs that, and what it does for each of them. Throughout, one line stays fixed: SimEngine is decision support and scenario analysis. It does not give financial advice and it issues no buy or sell signals.

**The word you'll see most: Monte Carlo simulation.** That just means running the same scenario thousands of times, each time with slightly different guesses for the things you're unsure about, then looking at all the results together. We call one such run a **future**. One future is one way things could play out. Thousands of futures show you the whole range.

**Two more words, defined once, because all four sections below use them:**

- **Median** — the middle result. Line up every future from worst to best; the median sits dead center. Half came out better, half worse.
- **80% range** — the band where 8 out of 10 futures landed. The other 2 split off above and below it. It tells you what "normal" looks like, not just the average.

---

## 1. A regular person facing a big, hard-to-reverse decision

You are about to make a choice you can't easily take back. Quit your job and go freelance. Take the mortgage. Move across the country for a new role. These decisions usually get made on a single mental estimate ("I think I'll make about $100k") and a gut feeling. The estimate is probably wrong, and worse, it hides how wrong it could be.

**The job to be done:** see the realistic range of outcomes before you commit, not just the optimistic middle.

Take a real one. You're a freelance developer or designer asking, "Can I go full-time freelance and sustain a livable income?" You start the year with **$20,000 in savings**. Here is what SimEngine reported across 5,000 simulated futures of your next year:

| Outcome | Median (the middle future) | 80% range (8 of 10 futures land here) |
|---|---|---|
| Annual gross income | $107,317 | $78,065 to $137,738 |
| Annual net income | $27,298 | $2,521 to $53,064 |
| Ending savings | $47,298 | $22,521 to $73,064 |
| Effective hourly rate | $33 | $4 to $53 |

Read the rows together and they hang together. Gross income is everything you bill. Net income is what you keep after taxes and expenses, with a median of $27,298. Ending savings is your starting $20,000 plus that net income, which is why the savings row sits exactly $20,000 above the net-income row.

Now look at what the table tells you that a single estimate never would. Gross income looks great near $107k, but the money you actually keep has a median of just $27,298 and can dip near $2,500 in a lean year.

The effective hourly rate is the surprise. It is your gross income divided by every hour you put in, including the unpaid hours spent hunting for the next client. It runs about $33 in the middle but drops to roughly $4 in the worst cases. Income stays positive in those bad futures, but you earn it by grinding far more hours for far less work, so your pay per hour collapses toward minimum wage even when the dollars never go negative.

And yet the decision still looks viable. SimEngine ran three **safety checks**, plain limits you set on how much risk you'll tolerate, and all three passed:

- Chance your savings go negative: **0.66%** (your limit was 10%). Well under.
- Chance gross income falls below $60k: **1.86%** (your limit was 25%). Well under.
- Your worst-case average loss: **-$6,206** (your limit was -$20,000). This one takes the 500 worst futures out of 5,000 and averages their net income. A loss of $6,206 is a smaller loss than the $20,000 you said you could stomach, so it passes.

So the answer is: yes, this looks survivable, with eyes open about the lean stretches. That is a far better thing to know going in than "I'll probably clear six figures." The mechanism is simple. You describe your unknowns once, SimEngine runs the year 5,000 times, and you see the whole spread, including the months that would scare you.

---

## 2. A small business owner or independent consultant

You're running something small, and the hard questions are all about money over time. What should I charge. How long until I run out of cash. Can I afford to hire. A spreadsheet gives you one tidy projection. It cannot tell you the odds that the plan quietly fails.

**The job to be done:** stress-test a pricing, runway, or hiring plan against its risks, and find the settings that hit your goal without blowing past your limits.

Here's the warning case. An indie software founder asks, "Should I go full-time on this, and how much runway do I need?" Across 5,000 futures, the steady income that repeats each month (your **monthly recurring revenue**, or MRR) grows nicely to a median of $2,088 by month 24. A spreadsheet would stop there and look fine. SimEngine kept going and showed the part the spreadsheet hides:

- Ending cash, median: **-$33,205** (80% range -$38,483 to -$27,431). Every number here is negative. Even the better end of the range still owes money; -$38,483 is the worse end, -$27,431 the less-bad one.
- Months to profit: **24**. It never turns a profit inside the two-year window.
- Chance of ending underwater (cash below $0): **100%**. Every single future ran out of money.

All safety checks failed. Revenue was climbing the whole time, but the business bled cash every month. The one-number forecast, "MRR around $2,088 by month 24," completely buried the fact that you'd go broke getting there. That gap between the tidy number and the real risk is the entire reason this tool exists.

Once you can see the risk, you can fix the plan. SimEngine includes an **optimizer**, a search routine that automatically tries thousands of combinations of the settings you control, such as your price, and finds the ones that score best while staying inside the safety limits you set. You mark which inputs it's allowed to change, you define what "good" means (for example: get ending cash as high as possible while keeping the chance of running out below 10%), and it hunts for the configuration that gets you there without crossing your risk lines. You don't tune the price by hand and hope. You let it search.

---

## 3. Builders putting AI agents in charge of real actions

You're wiring up an AI agent, software that acts on its own, to do things in the world: approve a refund, set a price, send the order, move the budget. The danger isn't that the model sounds unsure. It's the opposite. Language models state confident single guesses, and when one agent's overconfident guess feeds the next step, small errors compound into a bad action nobody checked.

**The job to be done:** give an agent a way to pause and ask "are the actual outcomes safe enough to proceed?" before it acts.

SimEngine can run so that an AI agent talks to it directly. The agent pauses and asks SimEngine a question the way you'd ask a calculator, gets an answer, and only then acts. (The plumbing for this is called an MCP server, a standard way for AI software to call outside tools. SimEngine offers nine such tools.) The one that matters here is a command literally named `decide_under_uncertainty` (the monospaced text is the exact name the agent types). The agent hands it a metric it cares about, an acceptable range (a minimum, a maximum, or both), and a minimum confidence level (0.8 by default, meaning 80%). SimEngine simulates the outcomes and answers:

- A verdict: **proceed** or **escalate** (escalate means hand it to a human).
- `probability_within_bounds`: the share of simulated futures that landed inside the acceptable range.
- The full range of outcomes, plus a plain-English reason for the verdict.

So instead of acting on one confident point guess, the agent asks the uncertainty calculator whether enough futures actually fall in the safe zone. If not, it escalates rather than compounding the error. One honest distinction: this measures **outcome risk**, the spread of real-world results given uncertain inputs. It does not measure the model's own confidence in its words. It tells the agent whether the situation is safe, not whether the model feels sure.

---

## 4. Forecasters and the prediction-market moment

You make calls about uncertain future events, and you want to know two things: am I starting from a good estimate, and over time, am I actually any good at this? Most forecasting happens with no scorekeeping, so nobody ever finds out whether their gut is **calibrated** (your stated confidence matches how often you turn out to be right) or just loud.

**The job to be done:** start from a market-tested probability, fold in your own evidence, and keep an honest track record of your accuracy.

SimEngine can pull a live price from **Polymarket**, a prediction market where people bet real money on whether future events happen, so its prices act as crowd-sourced probabilities. If people will pay 60 cents for a contract that pays $1 when the event happens, the crowd is effectively saying it's 60% likely. The optional `feeds/polymarket.py` part of the software turns that price into a calibrated **prior**, a starting probability for one of your unknowns. From there you refine it with your own data as evidence arrives. The market gives you a sensible starting point instead of a number you made up. This is opt-in and the only part of SimEngine that ever touches the network. The price is an input to your private simulation, never a rebroadcast feed and never a trade signal.

Then you keep score. The `calibration.py` part of the software keeps a small local ledger where you record each forecast now and resolve it against what actually happened later. It scores you with a **Brier score**, a standard measure of forecast accuracy where lower is better:

- **0.0** is perfect.
- **0.25** is what you'd get by always shrugging and saying 50/50.
- **1.0** is the worst possible.

One worked example: if you said 70% and the thing happened, your score for that call is 0.09, which is good. Over months, that ledger turns "I'm usually right" into a number you can check. That track record is the thing that proves the engine, and your judgment, are actually calibrated rather than just confident.

---

## The common thread

Four very different users, one underlying need: stop pretending the future is a single number. The freelancer sees the lean months coming. The founder sees the cash run out before it happens. The agent escalates instead of guessing. The forecaster builds a track record instead of a hunch.

SimEngine shows you the range, the odds, and the risks, so you decide with your eyes open. It is decision support and scenario analysis. It does not give financial advice and it issues no buy or sell signals.

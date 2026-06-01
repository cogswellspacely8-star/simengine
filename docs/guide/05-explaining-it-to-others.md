# Explaining It to Others (Pitch Kit)

This is the page you read right before you walk into the room. It gives you the words.

## If you only read this far

Most plans live in a spreadsheet that gives you one number. One number hides everything that matters: the bad cases, the odds, the point where you run out of money.

**SimEngine is a calculator for uncertainty: you describe a decision and its unknowns, and it shows you the full range of what could happen, how likely each outcome is, and where the risk lives.**

Picture a flight simulator. A pilot doesn't learn to handle an engine failure by crashing a real plane. They practice it a hundred times in a simulator first. SimEngine lets you crash your business plan safely, over and over, before you bet real money on it.

If you remember nothing else, remember those three things. The rest of this page is the elevator pitch, the questions you'll get, and the limits you should name out loud.

---

## The one-sentence definition

**SimEngine is a calculator for uncertainty: you describe a decision and its unknowns, and it shows you the full range of what could happen, how likely each outcome is, and where the risk lives.**

If you only remember one line, remember that one.

---

## The 30-second elevator pitch

> Most plans live in a spreadsheet that gives you one number. One number hides everything that matters: the bad cases, the odds, the point where you run out of money. SimEngine replaces that single guess with thousands of possible futures. You write down a decision and the things you're unsure about — growth rate, costs, how many customers sign up — and it runs the whole thing five thousand times, with different luck each run. Out comes a real answer: not "you'll make $30,000," but "here's the middle outcome, here's the best and worst 1-in-10, and here's a 100% chance you run out of cash inside two years." It runs on your own computer, needs nothing installed, and AI assistants can use it on their own. It's a way to make a decision with your eyes open.

Time it. It lands in about thirty seconds at a normal pace.

---

## Analogies that land

Pick the one that fits your audience. Each one is doing the same job: turning "thousands of possible futures" into something a person can picture.

**A flight simulator for decisions.** A pilot doesn't learn to handle an engine failure by crashing a real plane. They practice it a hundred times in a simulator first. SimEngine lets you crash your business plan safely, over and over, before you bet real money on it.

**A weather forecast for your plan.** A forecast doesn't say "it will rain." It says "70% chance of rain, with a storm risk by Friday." That's exactly what SimEngine gives you: "70% chance this plan turns a profit, and here's how bad the unluckiest 1-in-10 gets." You'd never plan a wedding off a forecast that just said "weather: yes." Stop planning your business off one either.

**A crash-test dummy for your spreadsheet.** Your spreadsheet tells you what happens when everything goes to plan. SimEngine straps it in and runs it into the wall a few thousand times to show you what actually breaks, and how often.

---

## Why now

Probabilistic thinking — reasoning in odds and ranges instead of single guesses — just went mainstream. Two things pushed it there at once:

- **AI agents need a real way to reason about uncertainty.** Language models are confident narrators. Ask one "should I do this?" and it gives you a fluent answer with no sense of the odds. Agents that act in the real world need to weigh outcomes, not just sound sure. SimEngine gives them an actual engine for that, callable over a standard interface.
- **Prediction markets went mainstream.** Prediction markets are sites where people bet real money on whether an event will happen, which turns the crowd's belief into a live price you can read as odds. Kalshi and Polymarket put those money-backed odds on real-world events in front of millions of people. "What are the odds?" is now a normal question to ask about anything, not just sports.

The short version: the world started thinking in odds, and the tools to do it well were missing. We build that tool.

---

## The five questions you'll get

You will hear these. Here are the answers, tight.

**1. "Isn't this just guessing?"**
No. It's structured guessing, which is the only honest kind. You don't enter a single made-up number — you enter a range and a shape (a shape — how the odds cluster, so "most likely around 5%" weighs more than the edges). "Growth is probably 5% a month, but could be 2% to 9%." The engine respects that honesty and carries it all the way through to the answer. A spreadsheet forces you to pretend you know the exact number. SimEngine lets you admit you don't, then does the math on your uncertainty properly. And it keeps score: every forecast gets logged and later checked against what actually happened, so over time you can prove how accurate it's been.

**2. "How is it different from a spreadsheet?"**
A spreadsheet computes one future. SimEngine computes thousands and shows you the spread. Here's a real case — a "should I go full-time?" plan for a freelancer. The gross income looked great: a median around $107,000 a year. Median means the middle outcome — line up all the runs from worst to best, and half came out better, half worse. But the engine showed net income (after taxes and expenses) was far lower and lumpier: a median near $27,000, with worst-case effective pay around $4 an hour in the slow stretches when work dries up. A spreadsheet would have shown only the rosy gross number. The middle outcome and the bad cases are exactly what it hides.

The SaaS case is starker. We ran an indie software plan — 5,000 possible futures, each with different luck. MRR (monthly recurring revenue — the predictable income from subscriptions) reaches about $2,088 by month 24. Sounds like a slow, steady climb. But SimEngine ran the cash alongside it and reported a median ending cash of **-$33,205**, with a **100% chance of running out of money** before the 24-month window closes. All five thousand runs ran out of cash. The one-number spreadsheet hid the one fact that should have stopped the founder cold. That gap is the entire reason this exists.

**3. "Is this gambling? Is it financial advice?"**
Neither. It gives you no buy or sell signals and tells you to bet on nothing. It's decision-support: scenario analysis for your own plan. When it reads a live market price — say from Polymarket — that number goes in as one input to your simulation, the same way a weather model uses today's temperature. It is never a trade tip and never a rebroadcast feed. SimEngine is not financial advice. It's a thinking tool, and it stays firmly on that side of the line.

**4. "Why would an AI need this?"**
Because an AI sounds certain even when it shouldn't be, and "sounding sure" is not the same as "being right." Ask an AI "will this product launch hit its numbers?" and it writes a confident paragraph either way — that confidence is about its wording, not about the actual odds. SimEngine measures the real risk in the outcome instead: the spread of results once you account for the unknowns. Concretely, an agent can ask "should we proceed?", hand over the metric and an acceptable range, and get back a clear "proceed" or "escalate," the probability the result lands in bounds, and a plain-English reason. The AI stops bluffing and starts showing its work.

**5. "What stops someone from just copying it?"**
The code is open — copying it is the easy part, and we want people to use it. What can't be copied is the track record. SimEngine logs every forecast and scores it against reality as outcomes come in: when it says "70% chance," it later checks how often 70%-odds calls actually came true, and grades the gap. That ledger compounds month over month. A competitor can clone the engine in a weekend. They cannot clone two years of proven accuracy. Trust is the moat, and trust only accrues with time.

---

## What it is NOT

Say these plainly. Naming the limits is what makes the rest believable.

- **Not a crystal ball.** It doesn't predict the future. It maps the range of futures your own assumptions imply. Garbage in, garbage out — but at least you'll see the full range of the garbage.
- **Not financial advice.** No buy/sell signals, ever. Decision-support only.
- **Not a trading feed.** When it uses a market price, that's an input to your simulation, not a signal to rebroadcast or act on.
- **Not a measure of an AI's confidence.** It measures the risk in an outcome — how widely results spread once you account for the unknowns — not how sure a language model sounds about its own words.
- **Not magic, and not heavy.** It runs on your own computer and needs nothing installed beyond the language it's written in. The honesty is the feature, not the complexity.

---

## One last thing to leave them with

A single number gives you false confidence. A range gives you real readiness. Take that freelancer again: the gross income looked great, a median around $107,000 a year, but net income came in with a median near $27,000 and worst-case effective pay around $4 an hour in the lean stretches. The difference between those two pictures is the difference between walking in blind and walking in ready. That's what we build.

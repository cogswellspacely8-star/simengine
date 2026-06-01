# What Is SimEngine?

You make decisions about the future every day. Some are small. Some change your life. And almost all of them come down to a single guess.

"I'll make about $100k freelancing."
"This project will take three months."
"We'll have enough savings to last until the business pays for itself."

Each of those is one number. And that one number is a lie — not because you're wrong, but because the future was never going to be one number. It's a range. Some futures are better than your guess. Some are much worse. The single number you wrote down hides every one of them, and the worst ones are exactly the ones that hurt.

SimEngine fixes that. Think of it as a calculator for uncertainty.

A normal calculator takes numbers you're sure about and gives you one answer. SimEngine takes the things you're *not* sure about — your unknowns — and gives you the full picture: every way the future could plausibly play out, how likely each one is, and where the danger sits.

## How it works, in one breath

You describe a decision and its unknowns in plain terms: what you control, what you don't, and how those things turn into an outcome you care about. For each unknown, you don't give one number — you give a realistic range. "Somewhere between 8 and 20 clients a year, usually around 12." SimEngine then plays the future out thousands of times. Each play-through reaches into the ranges you gave it, picks a value from inside each one, runs them forward, and records what happened. It never invents numbers from thin air — it only draws from the ranges you set.

This repeated play-it-out-many-times method has a name — **Monte Carlo simulation** — but the name doesn't matter. It works the way rolling dice thousands of times teaches you the odds: one roll tells you nothing, but ten thousand rolls show you the real shape of what's likely. Instead of one guess, you get thousands of possible futures, sorted and counted.

One thing up front: SimEngine is only as honest as the ranges you feed it. Careful ranges give you a useful map. Sloppy ones give you a precise, confident map of nonsense. More on that at the end.

## A real example: should I go freelance?

Here's a real decision a person might face: *Can I go full-time freelance and still make a living?*

You'd normally answer it with a back-of-the-envelope number. Maybe you look at your rate, your hours, and figure you'll gross around $100k. Sounds good. Quit the job.

We ran this exact decision through SimEngine — 5,000 simulated years of freelancing, each with slightly different luck on how many clients show up, how many hours you bill, and what slips through the cracks. We gave it one more starting fact: you begin with $20,000 in savings. Here is what came back.

| What you care about | Typical result (median) | The likely range |
|---|---|---|
| Gross income (before costs) | $107,317 | $78,065 to $137,738 |
| **Net income (what you keep)** | **$27,298** | **$2,521 to $53,064** |
| Ending savings | $47,298 | $22,521 to $73,064 |
| Effective hourly rate | $33/hr | $4/hr to $53/hr |

A few words on how to read that.

- The **median** is the middle outcome: half the simulated futures came out better, half worse.
- The **range** shown is the middle 80% — 1 in 10 futures landed below the low end, and 1 in 10 landed above it. It's the band where life usually lands, not the floor or the ceiling. Worse things can happen below that low end. Those rare, ugly outcomes — the "tails" — matter, and we come back to them.
- **Gross income** is all the money passing *through* the business. **Net income** is what's left after taxes, business costs, and the pay you draw out for yourself — the money you actually keep. That's why the two numbers are so far apart.
- **Ending savings** starts from the $20,000 you began with and adds the year's net income. Median net of $27,298 on top of $20,000 lands you near $47,298.
- **Effective hourly rate** is what you really earned per hour: what you kept, divided by every hour you worked — billable or not.

Now look at what the single number hid.

Gross income looks great — about $107k, right where the back-of-the-envelope guess landed. But that's money passing through, not money you keep. **Net income — what's actually left — has a median of just $27,298.** And it's wildly uneven: in the leaner 1-in-10 futures it's barely over $2,500 for the whole year. The effective hourly rate tells the same story. Typically $33/hr, fine — but in the leaner 1-in-10 futures it drops to about **$4 an hour**, below minimum wage. And remember: below that 1-in-10 mark, a few futures are worse still.

That is the risk a single "$100k" would have buried completely.

So is freelancing a bad idea here? No — and this is the part that matters. SimEngine also checked the question you actually care about: *will I run out of money?* Across all 5,000 futures, ending savings dropped below zero only **0.66% of the time** — less than a 1-in-100 chance. That tiny number lives in the tails, below the everyday range in the table — exactly the kind of rare, ugly outcome the middle 80% doesn't show. SimEngine counts it anyway. It also found under a 2% chance of grossing below $60k — roughly what a steady day job might pay, and a fair line for "this isn't working."

The honest read: the headline income is softer and lumpier than it looks, you should brace for lean months, but you almost never go broke. Going full-time is viable — with your eyes open. That's a far better decision than either blind optimism ("$100k, easy!") or blind fear ("too risky, don't quit"). You can see the whole thing.

## What makes this more than a spreadsheet

A spreadsheet gives you one number per cell. SimEngine does three things a spreadsheet can't.

**1. It shows the full range, not one number.** You don't get "$27k." You get the whole spread — the good futures, the bad futures, and how common each is. The median *and* the lean months, in the same view.

**2. It speaks risk in plain language.** Not just charts — actual sentences you can act on. "Less than a 1% chance of running out of savings." "Under 2% chance of grossing below $60k." Risk you can repeat to a partner, a lender, or yourself at 2 a.m.

**3. The same engine works for a person or an AI.** You can drive it yourself through a local web page in your browser — type in your numbers, read the results. An AI assistant can drive that same engine the same way, automatically, to check its own plans against reality before it acts. One engine, one set of answers, whether a human or a machine is asking.

## What SimEngine is *not*

We'll be straight with you about the limits.

- **It is not a crystal ball.** It does not predict *the* future. It maps the futures that are plausible given what you tell it. The actual future is one draw from that range — and it could land anywhere in it, including the tails.

- **It is not financial advice.** SimEngine is for thinking through decisions and scenarios. It does not tell you to buy, sell, or invest in anything, and it issues no trading signals. It's a tool for your judgment, not a replacement for it.

- **It is only as good as your assumptions.** SimEngine doesn't know your business. It takes the unknowns *you* describe and plays them out honestly. Feed it sloppy guesses and you get a precise, confident map of nonsense. Feed it careful, honest assumptions and it will show you things a single number never could.

That last point is the whole deal. SimEngine won't think for you. It takes your real uncertainty seriously, plays it out thousands of times, and hands you back the full range — so you decide with the risk in plain sight instead of hidden behind one hopeful number.

Ready to run your first simulation? It happens on a simple web page in your browser — you fill in your numbers and read the results, no coding required. That's the next document.

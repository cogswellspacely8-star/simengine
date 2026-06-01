# Quickstart: Your First Simulation

You are about to run a real decision model in under two minutes. No account, no sign-up, no packages to download. The only thing you need is Python already on your computer (almost every Mac and Linux machine has it) and a browser.

By the end, you will have watched SimEngine play out 5,000 possible futures for a small software business and catch a problem that a normal spreadsheet would have hidden completely.

Let's go.

---

## Step 0: Do you have Python?

SimEngine runs on Python, the programming language. You don't have to write any of it — you just need it installed. Most Macs and Linux computers come with it. Here's how to check.

A **terminal** is the plain text window where you type commands instead of clicking buttons.

- **Mac:** Press `Cmd + Space`, type `Terminal`, hit Enter.
- **Windows:** Press the Start key, type `cmd`, hit Enter.
- **Linux:** You already know where your terminal is.

In that window, type this and press Enter:

```bash
python3 --version
```

If you see a number like `3.8` or higher, you're set — skip to Step 1. If you see an error, install Python from [python.org](https://www.python.org/downloads/) (it's free, takes a couple of minutes), then come back.

---

## Step 1: Start it

A **folder** is just the directory where SimEngine's files live after you downloaded them. In your terminal, you need to move into that folder, then start the program. Type this and press Enter:

```bash
cd v3 && python3 server.py
```

That command does two things: `cd v3` steps into the `v3` folder, and `python3 server.py` starts SimEngine.

Then open this in your browser:

```
http://localhost:8420
```

That's the address of the page SimEngine is now serving from your own computer. There's nothing to install. SimEngine is pure Python — it runs on the standard library that ships with Python itself (version 3.8 or newer). No packages to download, no build step, no dependencies.

The whole interface is a single web page served from your own machine. Nothing leaves your computer.

---

## Step 2: What you're looking at

The page shows a list of **domains**. A domain is one ready-made decision model — a real question someone faced, written down as a config the engine can run. Each one describes a decision, the things you can't know for sure, and what you're trying to figure out.

You'll see examples like a SaaS startup, a freelance career, and others. Each is a self-contained `.json` file. Later you'll write your own, but today you'll run one that's already there.

---

## Step 3: Run "Indie SaaS — MRR Growth & Runway"

Two quick definitions before you click, because the question below uses both:

- **MRR** is monthly recurring revenue — the subscription money coming in each month.
- **Runway** is how long your cash lasts before it runs out.

Now click **Indie SaaS — MRR Growth & Runway**, then hit **Run**.

This domain asks a question a lot of people actually face:

> Should I go full-time on this SaaS, and how much runway do I need?

### What just happened

This is the core idea, so slow down here. Instead of guessing one number for each unknown — how fast you'll add customers, how many will cancel, what you'll spend — SimEngine picks a different plausible value for each one, then plays the whole 24-month story forward. Then it does that again. And again. Five thousand times. Each run is one possible future. Together, the 5,000 futures show you the full range of what could happen, not just one tidy guess.

Running one model thousands of times with different random inputs has a name: a **Monte Carlo** simulation. That's all the term means — roll the dice many times and look at the whole spread of results.

This takes a second or two. Then you get results.

---

## Step 4: Read the headline (and the "aha")

### The headline (looks fine)

Here are the numbers SimEngine reports for this model (5,000 simulated futures):

| Metric | Median (the middle outcome) | 80% range (8 out of 10 futures land here) |
| --- | --- | --- |
| Final MRR | $2,088 | $1,653 to $2,552 |
| Total revenue | $30,595 | — |
| Ending cash | **-$33,205** | -$38,483 to -$27,431 |
| Months to profit | 24 (never reaches profit in the window) | — |

Two terms in that table do a lot of work:

- **Median.** Line up all 5,000 results from worst to best; the median is the one smack in the middle — half the futures came out better, half came out worse. It's steadier than an average, which one freak result can yank around.
- **80% range.** The middle band where 8 out of 10 futures land. The other 2 out of 10 fell outside it — some better, some worse — but this band covers the bulk of what's likely.

Read the top line and you'd feel fine. Revenue climbs steadily. By month 24, monthly recurring revenue lands around **$2,088**. The business is growing.

Now read the cash line. Ending cash is about **$33,205 in the red** — that's the minus sign: negative, money gone. The business grows revenue the entire time and bleeds money the entire time.

### The safety checks (all failed)

This is the moment SimEngine exists for. It doesn't just hand you a happy middle number — it checks the risks. The model carries **safety limits**: the lines you decided you can't cross, written into the model beforehand. They aren't SimEngine's opinion — they're your rules. On this run every single one **FAILED**:

| Safety check | Result | Limit |
| --- | --- | --- |
| Chance of ending cash below $0 | **100%** | must stay under 15% |
| Chance of final MRR below $3,000 | **99.1%** | must stay under 25% |
| Average cash in the worst 10% of futures | **-$40,342** | must stay above -$15,000 |

Overall safety: **FAILED**.

That last row needs a word. To get it, you take the 500 ugliest futures — the worst 10% of the 5,000 — and average just those. It answers a question the median never will: when things go badly, how bad does it actually get? Here, the bad case is about $40,342 in the hole.

Now read the first row again. **100%.** Not "this is risky." Not "watch your cash." Every single one of the 5,000 futures ends with the business out of money. In plain terms: every imaginable version of this plan ends with you, personally, broke. There is no version of this plan, as written, where you don't run out of cash inside 24 months.

That's the whole point of SimEngine. A normal spreadsheet would have told you "MRR reaches about $2,088 by month 24" and stopped there — one confident number that quietly hides the fact that you'd be broke. SimEngine plays out the full range and shows you the part the single number was covering up.

The decision the model was asked to weigh — *go full-time, with how much runway?* — now has a real answer: not on these assumptions, not without changing the plan or raising a lot more cash.

And you don't have to stop at "no." Pull a lever and re-run: charge more per customer, lose fewer of them, or spend less each month. Watch the safety checks each time. That's how you turn a dead end into a plan that survives.

---

## Step 5: Prefer the command line? Skip the browser

You don't need the web UI at all. The same model runs straight from your terminal, and it finishes just as fast — a second or two, same as the browser:

```bash
python3 kernel.py domains/saas_startup.json --seed 42
```

The `--seed 42` part makes the randomness repeatable. A seed is just a starting point for the dice rolls — give it the same starting point and you get the exact same 5,000 futures every time, so your results match this guide and anyone else who runs it. Drop the seed and each run draws a fresh set of futures.

You'll get the same metrics, ranges, and safety verdict printed right in your terminal.

---

## Step 6: Make sense of every number

You just read the headline. Every figure on that results page means something specific — the median, the 80% range, the trajectory bands (lines showing the likely high-to-low path month by month), the histograms (bar charts that show how often each outcome came up), the single fitness score (one number grading the whole plan), and the plain-English narrative.

Next, read **Reading the Results**. It walks through each part of the output one piece at a time, so the next domain you run — or the first one you write yourself — tells you exactly what you need to know.

You ran your first simulation. Now you know what the numbers are hiding.

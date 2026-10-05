# Ask Anything & Track Your Predictions

The earlier documents show you how to run a model and how to write one. This one is the shortcut: **describe a decision in plain words and let SimEngine build the model for you — then keep score of how right it was.** No JSON, no terminal.

## Ask Anything — the fastest way in

Open `http://localhost:8420` and click **Ask anything**. Type a real question:

> "Should I take an $8k/mo, 6-month contract if there's a 30% chance it overruns?"

Pick a model, set the number of runs, and hit **Ask SimEngine**. Behind the scenes it:

1. Turns your question into a model (a config), checking and repairing it against the engine until it's valid.
2. Runs thousands of simulated futures.
3. Explains the answer in plain language — the bottom line, the likely range, and the risks.

Two things make this trustworthy rather than a black box:

- **It asks when your question is too vague.** "Will I win?" gets a few clarifying questions back ("Win what? What are the odds of one attempt?") instead of a confident, made-up answer.
- **It states its assumptions.** The answer opens with what the model assumed — especially anything you didn't specify — so you can correct it. The engine is only ever as good as those assumptions; this keeps them in the open.

You can **Save as Domain** to keep any generated model and re-run or tune it later.

## Models and speed

The "Ask anything" box runs against a **local model by default** — free, private, nothing leaves your machine. The dropdown lists the models you have installed (via [Ollama](https://ollama.com)); smaller ones are faster.

- **On a machine with a GPU**, local models answer in seconds. (If yours is running slow, the model may be on the CPU — make sure Ollama is using the GPU.)
- **On CPU only**, expect 30–90 seconds; pick a smaller model.
- **Want it instant and don't mind a hosted model?** Point the server at OpenAI-compatible or DeepSeek by setting an environment variable, and the dropdown switches to those models.

This is decision support, not financial advice — it never tells you to buy, sell, or bet.

## Track your predictions

A forecast you never check is just an opinion. Click **Predictions** (top of the sidebar) to open your track record:

- Every forecast the engine has logged, with its probability and the date it resolves.
- When the real outcome is known, click **Hit** or **Miss** to grade it.
- A **Brier score** builds at the top as you grade outcomes.

The Brier score is the scoreboard for calibration — *do things you call 70% actually happen about 70% of the time?* **Lower is better:** 0.0 is perfect, 0.25 is what you'd get always guessing 50/50, 1.0 is worst. You can also log a prediction by hand right in that view.

Why this matters: over time, a track record of low Brier scores is what turns "the engine said 64%" into "the engine has been right when it says 64%." That accumulated, checked record is the thing no one can fake — and it's exactly what makes a forecast worth acting on.

### Score against a baseline, not just against reality

A Brier score on its own cannot tell you whether the engine added anything —
a weather forecast of 30% rain is only good if it beats the base rate. So a
forecast can carry a **baseline**: the comparison probability (a base rate, a
published forecast, a market's implied probability) recorded at the same moment.
`POST /api/forecast` accepts `baseline_prob`, `baseline_source` and `model`;
`GET /api/forecasts` then reports **skill vs baseline** (`1 - brier_model /
brier_baseline`, positive means the engine beat it) and a per-model table.

For range questions — which temperature band, which CPI bucket — the
`forecast_buckets.py` tool records every bucket of an event from one run and
grades them all at once when the real value lands. That loop is described in
[docs/market-loop.md](../market-loop.md).

## Where this fits

- New to the whole idea? Start with [What Is SimEngine?](01-what-is-simengine.md).
- Want to read the raw numbers behind an answer? [Reading the Results](03-reading-the-results.md).
- Want to hand-build or tune a model? [Model Your Own Decision](06-model-your-own.md).

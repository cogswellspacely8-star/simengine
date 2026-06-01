# Start Here

SimEngine is a calculator for uncertainty. You describe a decision and the things you don't know yet in a short text file, run one command, and it plays out thousands of possible futures. Instead of one number ("I'll make about $100k"), you get the full range: the good cases, the bad cases, the odds of each, and where the risk hides.

A normal calculator answers "what is 7 times 8." SimEngine answers "if I'm not sure about five different things, how could this turn out, and how often does it go badly."

## Read in this order

| # | Document | What it does |
|---|----------|--------------|
| 1 | [What Is SimEngine?](01-what-is-simengine.md) | Why one number is a lie, and what to use instead. Start here if you've never heard of any of this. |
| 2 | [Quickstart: Your First Simulation](02-quickstart.md) | Run a real model in under two minutes. No sign-up, no installs beyond the Python you already have. |
| 3 | [Reading the Results](03-reading-the-results.md) | Make sense of the numbers, the bands, and the pass/fail flag the engine hands back. |
| 4 | [Who It Is For (and Why)](04-who-its-for.md) | The decisions this fits, the decisions it doesn't, and how to tell which one you've got. |
| 5 | [Explaining It to Others (Pitch Kit)](05-explaining-it-to-others.md) | The words to use when you walk into a room and have to explain it fast. |
| 6 | [Model Your Own Decision](06-model-your-own.md) | Write your own model from scratch, built up from the smallest working example. |

Keep the [Glossary](glossary.md) open in a tab. Every term in the guide is defined there in plain language, with a short note on why it matters.

The pitch kit (document 5) is the founder's cheat sheet for explaining SimEngine in one breath.

## What's free

The SimEngine engine — everything in this guide — is free and open source under the Apache 2.0 license. Run it, self-host it, build on it, at no cost. SimEngine is "open-core": the only paid piece is an optional hosted service (managed hosting for AI-agent use, run by OtrovertLabs) that you never need to run things yourself. Nothing you do on your own machine costs anything.

## Where to go next

- **Model your own decision** → [Model Your Own Decision](06-model-your-own.md). Turn your own question into a model.
- **Copy a working example** → browse the ready-made models in [`v3/domains/`](../../v3/domains/), or start from the annotated [`_template.json`](../../v3/domains/_template.json).
- **Go deeper** → the [project README](../../README.md) covers the full config schema, the command line, the HTTP API, and the tools for AI agents.
- **For AI agents** → [the decision gate](../decision-gate.md) and [real-time data feeds](../feeds.md).

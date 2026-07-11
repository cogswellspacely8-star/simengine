# Demand probe — `decide_under_uncertainty`

The #1 risk on the Calibration-MCP bet is "no agent builder asked for this."
Falsify it cheaply before investing weeks. Total cost: one post, 48 hours.

## Where to post

Pick 1–2 active agent-builder channels:
- AI Engineer / LangChain / LlamaIndex Discords
- Anthropic developer community (MCP channel)
- r/LocalLLaMA or r/AI_Agents (as a "would you use this" question, not a launch)

Post as a genuine question, not a product launch. No links on the first post —
you're measuring pull, not driving clicks.

## Draft post

> **Would you use a tool that stops your agent from acting on overconfident guesses?**
>
> Multi-step agents reason in single numbers — "this change nets ~$12k/mo" —
> and compound that error at every step. The number looks just as authoritative
> whether the inputs were solid or made up.
>
> I built an MCP tool, `decide_under_uncertainty`, that does this instead: you
> hand it a quick model of the decision (uncertain inputs as ranges/distributions)
> and the outcome you can live with. It runs a Monte Carlo simulation and returns
> the full **outcome distribution** plus a **proceed / escalate** flag — "82% of
> simulated futures keep cash above zero, that clears your 80% bar, proceed" or
> "only 61% do, escalate."
>
> It's modeling *outcome risk* (spread of results given uncertain inputs), not the
> model's token confidence — so the agent can gate its own actions on real tail
> risk before committing.
>
> Two questions:
> 1. Would you wire this into your agents?
> 2. Would you pay for a hosted version, or only use it if it's free/self-hosted?

## Decision rule

| Organic "I'd use this / send a link" responses in 48h | Action |
|---|---|
| **10+** | Demand is real. Proceed to Phase 1 full-speed: harden the tool, landing page, list on the Anthropic MCP registry + Cursor. |
| **3–9** | Lukewarm. Ship it free/open-source as a credibility piece; keep building the calibration ledger; re-probe after the Polymarket feed lands. |
| **~2** | The narrative beats the pull. Pivot effort to Edge Check (D1) — traders already pay for adjacent tools — and keep D2 as a free open-source artifact. |

Either way you learned it in two days, not two weeks.

## What's already built (so you can demo if asked)

- `decide_under_uncertainty` MCP tool — live in `v3/mcp_server.py`.
- Calibration ledger + scoring — `v3/calibration.py`.
- The pattern + examples — [`docs/decision-gate.md`](decision-gate.md).

## FINAL — posted text and log (2026-07-11)

Post text: the draft above, verbatim, with one addition at the end:
"(It's open source and runs with zero deps — `uvx simengine-mcp` — but I'm
asking about the idea, not driving installs.)"

Channels (pick both):
1. r/AI_Agents — as a "would you use this" question
2. Anthropic developer community MCP channel

Rules: post the same day in both; no other links; reply to every response;
do not post the landing page unless someone asks where to find it.

### Response log

| # | Channel | Response (quote/summary) | Signal (use / pay / no) | Timestamp |
|---|---------|--------------------------|--------------------------|-----------|
| 1 | | | | |

### Outcome (fill at +48h)

- Organic "I'd use this / send a link" count: __
- Tier per decision rule above: **10+ / 3–9 / ≤2** → __
- Phase 1 consequence: full build / free-tier-only build / stop

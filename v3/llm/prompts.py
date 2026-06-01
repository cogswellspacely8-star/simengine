#!/usr/bin/env python3
"""
Prompts for the NL->config compiler and the result explainer.

Kept compact and concrete so small local models (7B-class) stay on track:
a tight schema, the exact distribution and function names, and two short
few-shot examples drawn from real SimEngine configs.
"""

import json

# Two real, valid examples: the minimal coin-flip and a small business model.
_EXAMPLE_COIN = {
    "name": "Coin Flip",
    "n_simulations": 1000,
    "n_steps": 10,
    "parameters": {"heads": {"distribution": "bernoulli", "params": {"p": 0.5}}},
    "step_logic": [{"target": "payout", "expr": "1 if heads > 0.5 else -1"}],
    "accumulators": {"bankroll": "bankroll + payout"},
    "metrics": {"final_bankroll": {"expr": "bankroll", "format": "number"}},
    "initial_state": {"bankroll": 0},
}

_EXAMPLE_CONTRACT = {
    "name": "Take the contract?",
    "n_simulations": 5000,
    "n_steps": 6,
    "step_label": "month",
    "parameters": {
        "hours_per_week": {"distribution": "triangular", "params": {"low": 15, "mode": 25, "high": 45}},
        "overruns": {"distribution": "bernoulli", "params": {"p": 0.3}},
    },
    "controls": {"hourly_rate": {"distribution": "fixed", "params": {"value": 150}}},
    "initial_state": {"total_revenue": 0, "total_hours": 0},
    "step_logic": [
        {"target": "weekly_hours", "expr": "hours_per_week * (1.4 if overruns > 0.5 else 1.0)"},
        {"target": "monthly_hours", "expr": "weekly_hours * 4.33"},
        {"target": "monthly_rev", "expr": "min(monthly_hours, 160) * hourly_rate"},
    ],
    "accumulators": {
        "total_revenue": "total_revenue + monthly_rev",
        "total_hours": "total_hours + monthly_hours",
    },
    "metrics": {
        "total_revenue": {"expr": "total_revenue", "format": "dollar"},
        "effective_rate": {"expr": "total_revenue / total_hours if total_hours > 0 else 0", "format": "dollar"},
    },
    "safety": {
        "chance_constraints": [
            {"metric": "total_revenue", "condition": "below", "threshold": 30000, "max_prob": 0.25,
             "rationale": "No more than 25% chance of earning under $30k"}
        ]
    },
}


SYSTEM_PROMPT = (
    "You convert a person's real-world question about an uncertain decision into a "
    "SimEngine v3 domain config: a single JSON object that a Monte Carlo engine runs "
    "thousands of times to show the full range of outcomes.\n\n"
    "OUTPUT RULES:\n"
    "- Output ONLY one JSON object. No prose, no markdown, no code fences.\n"
    "- Model genuine uncertainty as ranges, not single guesses. The triangular "
    "distribution is your workhorse: {\"low\": worst, \"mode\": most likely, \"high\": best}.\n"
    "- This is decision support and scenario analysis, never financial advice or a trade signal.\n\n"
    "SCHEMA (top-level fields):\n"
    "- name (string), n_simulations (int, default 5000), n_steps (int), step_label (string, optional), seed (int, optional)\n"
    "- parameters: uncertain unknowns; controls: the person's decisions; exogenous: outside factors. "
    "Each variable is {\"distribution\": <name>, \"params\": {...}}.\n"
    "- initial_state: starting values for every accumulator you use.\n"
    "- step_logic: ordered list; each item is {\"target\": name, \"expr\": formula} (or \"sample\": {distribution}). "
    "Runs every step; later steps can use earlier targets.\n"
    "- accumulators: running totals, e.g. {\"cash\": \"cash + net\"}.\n"
    "- metrics: final outputs, e.g. {\"profit\": {\"expr\": \"cash\", \"format\": \"dollar\"}}. format is dollar|percent|number.\n"
    "- safety (optional): chance_constraints [{metric, condition: below|above, threshold, max_prob, rationale}] "
    "and cvar_constraints [{metric, alpha, min_cvar, rationale}].\n\n"
    "DISTRIBUTIONS: fixed{value}, uniform{low,high}, triangular{low,mode,high}, normal{mean,std,min?,max?}, "
    "lognormal{median,spread,min?,max?}, bernoulli{p}, poisson{lambda}, student_t{mean,scale,df,min?,max?}. "
    "There is no 'beta' distribution.\n"
    "EXPRESSION FUNCTIONS: min, max, abs, round, sum, len, int, float, sqrt, log, exp, ceil, floor, pow, "
    "random(), gauss(mu,sigma), binomial(n,p), clamp(val,lo,hi). Ternary works: \"A if cond else B\". "
    "The built-in _step is the current step number (starts at 1).\n\n"
    "COMMON MISTAKES — avoid every one:\n"
    "- Do NOT wrap a single number in sum(): write `units * price`, never `sum(units * price)`. sum() is only for a list.\n"
    "- A metric's expr must reference an accumulator or a step target BY NAME, e.g. {\"expr\": \"cash\"}. "
    "Never use dotted paths like `initial_state.cash`, never reference one metric from another metric, "
    "and never divide by a value that can be zero.\n"
    "- Every name in an expression must be a defined variable (parameter/control/exogenous), an earlier "
    "step target, or an accumulator. Do not invent names.\n"
    "- Put the running total you care about (cash, total_revenue) in `accumulators`, give it a starting "
    "value in `initial_state`, and report it as a metric. Profit each step = revenue - costs; cash accumulates profit.\n"
    "- Prefer ranges (triangular) for anything uncertain; use `fixed` only for things you truly know.\n\n"
    "EXAMPLE 1 (minimal):\n" + json.dumps(_EXAMPLE_COIN) + "\n\n"
    "EXAMPLE 2 (a real decision with a safety limit):\n" + json.dumps(_EXAMPLE_CONTRACT) + "\n"
)


def user_prompt(question, n_simulations=None):
    extra = f" Use n_simulations = {n_simulations}." if n_simulations else ""
    return (
        f"Build a SimEngine config that answers this question:\n\n\"{question}\"\n\n"
        "Pick sensible variables, ranges, step logic, and metrics that directly bear on the "
        "decision. Add a safety constraint for any 'I must not...' the question implies."
        + extra + " Output only the JSON object."
    )


def repair_message(errors):
    bullet = "\n".join(f"- {e}" for e in errors)
    return (
        "That config did not pass validation. Fix every problem below and return the FULL "
        "corrected JSON object (only JSON, no prose):\n" + bullet
    )


EXPLAIN_SYSTEM = (
    "You explain the results of a Monte Carlo simulation to the person who asked the original "
    "question. Answer their question directly and in plain language. Use ONLY the numbers you are "
    "given — never invent figures. Lead with the bottom line, then the likely range (p10 to p90), "
    "then the risks (the safety checks and the worst cases). Be honest about uncertainty. This is "
    "decision support, not financial advice. Keep it to a few short paragraphs; no markdown headers."
)


def explain_user_prompt(question, results):
    return (
        f"The person asked:\n\"{question}\"\n\n"
        "Here are the simulation results (JSON: per-metric stats with median and p10/p90, plus "
        "safety pass/fail and a plain narrative):\n\n"
        + json.dumps({
            "stats": results.get("stats", {}),
            "safety": results.get("safety", {}),
            "narrative": results.get("narrative", ""),
            "n_simulations": results.get("n_simulations"),
        }, default=str)
        + "\n\nWrite the answer to their question, grounded only in these numbers."
    )

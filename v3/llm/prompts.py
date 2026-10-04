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
    "lognormal{median,spread,min?,max?}, bernoulli{p}, poisson{lambda}, student_t{mean,scale,df,min?,max?}, "
    "beta{alpha,beta,low?,high?}, gamma{shape,scale|rate}, categorical{values,probs?}, empirical{values,jitter?}. "
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
    "- Per-step values are single numbers, NOT lists: never use sum(), len(), filter, lambda, or comprehensions on a step target or accumulator.\n"
    "- The ONLY names allowed are the functions listed above plus your own variables / step targets / accumulators. There is no `inf`, no `n_steps`, no `pi`. For 'no upper limit', just omit the upper bound or use a large number.\n"
    "- To report the CHANCE of something (e.g. the chance of losing money), use a safety chance_constraint — NOT a metric. Metrics are point quantities like final cash or total revenue.\n"
    "- Do NOT build percentage / ROI / profitability metrics that divide by a starting amount — there is no separate baseline name to divide by, and dividing by zero breaks the run. Report totals and final values (final_cash, total_profit) and let the reader judge.\n"
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


_ALLOWED_FUNCS_TEXT = ("min, max, abs, round, sum, len, int, float, sqrt, log, exp, ceil, "
                       "floor, pow, random, gauss, binomial, clamp")


def repair_message(errors, available=None):
    bullet = "\n".join(f"- {e}" for e in errors)
    msg = (
        "That config did not pass validation. Fix every problem below and return the FULL "
        "corrected JSON object (only JSON, no prose):\n" + bullet
    )
    if available:
        msg += (
            "\n\nIn expressions you may reference ONLY these names you have defined: "
            + ", ".join(available)
            + ".\nAnd ONLY these functions: " + _ALLOWED_FUNCS_TEXT
            + ".\nIf a metric or step references anything not in those lists, delete it or rewrite "
            "it using only those names. Keep metrics simple — report final totals or values "
            "(e.g. final cash, total revenue), not ratios that need a baseline."
        )
    return msg


CLARIFY_SYSTEM = (
    "You decide whether a question has enough concrete detail to build a useful Monte Carlo "
    "decision model. READY means it names the quantities involved and at least rough numbers, "
    "ranges, odds, or a timeframe to work from. NOT READY means it is vague with no numbers or "
    "scope (e.g. 'will I win?', 'should I invest?', 'is this a good idea?'). If NOT ready, give up "
    "to 3 short, specific questions that would make it modelable — ask for the key numbers, odds, "
    "amounts, or timeframe. Do not be pedantic: if a reasonable model can be built, say ready. "
    "Return ONLY JSON: {\"ready\": true|false, \"questions\": [\"...\"]}."
)


def clarify_user_prompt(question):
    return f"Question:\n\"{question}\"\n\nReturn the JSON verdict."


COVERAGE_SYSTEM = (
    "You are a strict, skeptical auditor. You check whether a Monte Carlo simulation actually answers "
    "the user's question, or whether it is a reduced / unfaithful model. You are given the question, the "
    "metrics the simulation ACTUALLY computed (name -> expression), and the model's variables and step "
    "targets. Assume the model is partial until shown otherwise.\n"
    "- captured: specific things the question asked for that a listed metric genuinely provides.\n"
    "- missing: outputs the question explicitly asked for that have NO matching metric, plus important "
    "mechanisms the question described that the model clearly does not implement.\n"
    "- fidelity: 'full' only if the metrics address the question's main asks; 'partial' if it captures "
    "some but misses important asks; 'low' if the metrics barely relate to what was asked.\n"
    "Be strict: if the question asks for a ratio, a probability, a specific year, several sub-questions, "
    "or a sensitivity analysis and there is no metric for it, that is missing. Return ONLY JSON: "
    "{\"fidelity\":\"full|partial|low\",\"captured\":[...],\"missing\":[...],\"note\":\"one short sentence\"}."
)


def coverage_user_prompt(question, metrics, variables, targets):
    return (
        f"QUESTION:\n\"{question}\"\n\n"
        f"METRICS THE SIMULATION COMPUTED (name -> expr): {json.dumps(metrics, default=str)}\n"
        f"MODEL VARIABLES: {json.dumps(variables, default=str)}\n"
        f"MODEL STEP TARGETS: {json.dumps(targets, default=str)}\n\n"
        "Audit how faithfully this simulation answers the question. Return the JSON verdict."
    )


EXPLAIN_SYSTEM = (
    "You explain the results of a Monte Carlo simulation to the person who asked the question. "
    "This is decision support, not financial advice. A few short paragraphs; no markdown headers.\n"
    "HARD RULES — breaking these is the worst thing you can do:\n"
    "- Report ONLY quantities that appear in the metric stats you are given. NEVER invent a number, a "
    "year, a ratio, a probability, or a percentile that is not in the data.\n"
    "- If the question asked for something the model did NOT compute (you will be told what is missing), "
    "say plainly 'the model did not compute X' — do NOT make up a value for it.\n"
    "- If you are told the model is reduced/partial, OPEN by saying so clearly, so the reader knows the "
    "answer covers only the simplified model.\n"
    "STRUCTURE: (1) one sentence of assumptions/limits, including what was NOT modeled; (2) the bottom "
    "line using only real metrics; (3) the likely range (p10-p90) and risks. Be honest about uncertainty."
)


def _input_assumptions(config):
    if not isinstance(config, dict):
        return {}
    return {cat: config[cat] for cat in ("parameters", "controls", "exogenous")
            if isinstance(config.get(cat), dict) and config[cat]}


def explain_user_prompt(question, results, config=None, coverage=None):
    stats = results.get("stats", {})
    payload = {
        "stats": stats,
        "safety": results.get("safety", {}),
        "narrative": results.get("narrative", ""),
        "n_simulations": results.get("n_simulations"),
    }
    inputs = _input_assumptions(config)
    extra = ("\n\nThe model's INPUTS (assumptions to state and let the reader correct):\n"
             + json.dumps(inputs, default=str)) if inputs else ""
    ground = ("\n\nThe ONLY quantities the simulation computed are these metrics: "
              + json.dumps(list(stats.keys())) + ". Report nothing outside this list.")
    cov = coverage or {}
    missing = cov.get("missing") or []
    cov_note = ""
    if missing:
        cov_note = ("\n\nThe model did NOT compute or model these things the question asked for — say so "
                    "plainly and invent no values for them: " + json.dumps(missing, default=str))
    if cov.get("fidelity") in ("partial", "low"):
        cov_note += "\n\nThis is a REDUCED model — open your answer by making that clear."
    return (
        f"The person asked:\n\"{question}\"\n\n"
        "Simulation results (JSON: per-metric stats with median and p10/p90, plus safety and a narrative):\n\n"
        + json.dumps(payload, default=str)
        + extra + ground + cov_note
        + "\n\nWrite the answer, grounded only in the metrics above, opening with the assumptions and any reduced-model caveat."
    )

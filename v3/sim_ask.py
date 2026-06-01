#!/usr/bin/env python3
"""
sim_ask — ask SimEngine any question of uncertainty, in plain language.

    python3 sim_ask.py "Should I take an $8k/mo, 6-month contract if there is a
                        30% chance it overruns?"

It uses a (local, by default) LLM to turn your question into a SimEngine config,
validates and repairs it against the engine, runs thousands of simulations, and
explains the result. Pure stdlib + the opt-in llm/ module; no dependencies.

Backend defaults to Ollama on localhost. Set SIMENGINE_LLM_BACKEND=openai (with
OPENAI_API_KEY) or =anthropic to use a hosted model instead.
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm.ask import answer_question
from llm.backends import LLMError


def _fmt(val, fmt):
    try:
        if fmt == "dollar":
            return f"${val:,.0f}"
        if fmt == "percent":
            return f"{val * 100:.1f}%"
        return f"{val:,.2f}"
    except (TypeError, ValueError):
        return str(val)


def _print_human(res):
    print()
    print(res["explanation"])
    print("\nKey numbers:")
    for m, s in res["results"]["stats"].items():
        label = m.replace("_", " ").title()
        fmt = s.get("format", "number")
        print(f"  {label}: median {_fmt(s['median'], fmt)} "
              f"(80% range {_fmt(s['p10'], fmt)} to {_fmt(s['p90'], fmt)})")
    safety = res["results"].get("safety") or {}
    if "all_passed" in safety:
        verdict = "ALL PASSED" if safety["all_passed"] else "FAILED — there are real risks here"
        print(f"\nSafety: {verdict}")
    print(f"\n(based on {res['results']['n_simulations']:,} simulations; "
          f"{res['attempts']} model attempt(s))")


def main(argv=None, _complete=None):
    p = argparse.ArgumentParser(prog="sim_ask",
                                description="Ask SimEngine any question of uncertainty.")
    p.add_argument("question", help="Your question, in plain language")
    p.add_argument("--backend", default=None, help="ollama (default) | openai | anthropic")
    p.add_argument("--model", default=None, help="Override the model name")
    p.add_argument("-n", "--n", type=int, default=None, dest="n", help="Number of simulations")
    p.add_argument("--seed", type=int, default=42, help="Random seed (default 42)")
    p.add_argument("--max-repairs", type=int, default=3, dest="max_repairs",
                   help="Max validate/repair rounds (default 3)")
    p.add_argument("--save", metavar="NAME", default=None,
                   help="Save the generated config to domains/NAME.json")
    p.add_argument("--show-config", action="store_true", help="Print the generated config")
    p.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable output")
    args = p.parse_args(argv)

    if not args.as_json:
        print("Thinking…", file=sys.stderr)

    try:
        res = answer_question(
            args.question, n_simulations=args.n, seed=args.seed,
            max_repairs=args.max_repairs, backend=args.backend, model=args.model,
            _complete=_complete,
        )
    except LLMError as e:
        print(f"\nLLM backend error: {e}", file=sys.stderr)
        return 2

    if not res["valid"]:
        if args.as_json:
            print(json.dumps(res, default=str))
        else:
            print("\nCouldn't build a valid model after several tries. Problems:", file=sys.stderr)
            for err in res["errors"]:
                print(f"  - {err}", file=sys.stderr)
        return 1

    if args.save:
        from server import save_domain
        saved = save_domain(args.save, res["config"])
        if not args.as_json:
            print(f"Saved as domains/{saved}", file=sys.stderr)

    if args.as_json:
        print(json.dumps(res, default=str))
    else:
        if args.show_config:
            print("\nGenerated config:")
            print(json.dumps(res["config"], indent=2))
        _print_human(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

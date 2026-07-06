# SimEngine MCP Server Card — DRAFT (not published)

status: **draft** — registry publication is a separate, explicitly gated
decision. Nothing in this file has been submitted anywhere.
date: 2026-07-06

---

## Name

SimEngine — Monte Carlo decision intelligence

## One-line description

Give your agent a real outcome-distribution calculator: validated,
schema-contracted Monte Carlo simulation across 18+ domains, with a numeric
calibration ledger and a proceed/escalate decision gate.

## Description

SimEngine lets an AI agent replace point-estimate guesses with simulated
outcome distributions. The agent describes a decision as a JSON config
(uncertain parameters, decision levers, external shocks, step logic, metrics,
risk constraints); the engine runs thousands of futures and returns
distributions, chance-constraint/CVaR safety verdicts, and optionally an
evolutionary optimum over the decision levers.

What makes it trustworthy rather than merely plausible:

- **Schema-contracted.** The config format is published JSON Schema
  (`GET /api/schema`); `validate_config` returns precise, machine-usable
  errors, so an agent can author a valid config in one or two shots.
- **Validated.** The forecast pipeline is backtested on ~2,800 walk-forward
  monthly forecasts over up to seven decades of public FRED data, scored with
  proper scoring rules (Brier, log loss, ECE). See
  `docs/backtests/2026-07-06-fred-monthly-calibration.md`.
- **Accounted for.** A sqlite calibration ledger records live forecasts and
  grades them against reality (Brier / log-loss / CRPS, reliability curve),
  so calibration is a number, not a claim.
- **Safe to run anywhere.** Pure Python stdlib (3.8+), zero dependencies,
  local-first; expressions evaluate in a whitelisted AST sandbox, never
  `eval()`.

Calls are synchronous: `simulate` returns full results in the same response
(typical run: a few seconds).

## Tools (9)

| Tool | What it does |
|------|--------------|
| `simulate` | Run a Monte Carlo simulation from an inline config or saved domain |
| `validate_config` | Check a config against the engine contract; precise errors |
| `list_domains` | List available example/saved domain configs |
| `optimize` | Evolutionary search over tunable levers, safety-penalized, returns `best_controls` |
| `update_bayesian` | Conjugate-prior update of a parameter from observed data |
| `convergence_check` | Is the sample size sufficient? |
| `sensitivity_analysis` | Which inputs drive the output (OAT with common random numbers) |
| `baseline_comparison` | Monte Carlo vs deterministic spreadsheet math |
| `decide_under_uncertainty` | Proceed/escalate gate: does enough probability mass land in the acceptable range? |

## Positioning guardrails (keep claims inside these lines)

- Say: "validated, schema-contracted Monte Carlo across 18+ example domains
  with a numeric calibration ledger and a historical backtest."
- Do NOT say: "the only general decision-intelligence MCP server"
  (fragile overclaim, flagged 2026-06) or anything implying async task
  handles (simulate is synchronous), market prediction skill, or financial
  advice.
- It models **outcome risk** (spread of results given uncertain inputs),
  not the language model's own confidence.

## Transport / install

- MCP over stdio: `python3 v3/mcp_server.py` (config template:
  `v3/mcp_config.json`)
- HTTP API on `localhost:8420`: `cd v3 && python3 server.py`
- Requirements: Python 3.8+. No pip install, no Docker, no Node.

## License

Open-core: engine Apache-2.0 (this repo); hosted MCP service commercial
(`LICENSE-COMMERCIAL.md`).

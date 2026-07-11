# simengine-mcp

<!-- mcp-name: io.github.cogswellspacely8-star/simengine -->

Monte Carlo decision intelligence over MCP. Give your agent a real
outcome-distribution calculator: schema-contracted simulation, chance/CVaR
safety constraints, sensitivity analysis, and a proceed/escalate decision
gate (`decide_under_uncertainty`) — all pure Python stdlib, zero
dependencies.

## Run

    uvx simengine-mcp

or add it to any MCP client as a stdio server with command `simengine-mcp`.

## Tools (9)

`simulate`, `validate_config`, `list_domains`, `optimize`,
`update_bayesian`, `convergence_check`, `sensitivity_analysis`,
`baseline_comparison`, `decide_under_uncertainty`.

## Validated

Backtested on 2,819 walk-forward monthly forecasts over up to seven decades
of public FRED data, scored with proper scoring rules (Brier, log loss)
plus calibration error (ECE). Details, source, docs, and the full engine (web UI, HTTP API):
https://github.com/cogswellspacely8-star/simengine

It models **outcome risk** — the spread of results given uncertain inputs —
as decision support. It is not financial advice and issues no trade signals.

License: Apache-2.0 (engine). A hosted service is offered separately under a
commercial license.

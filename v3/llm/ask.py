#!/usr/bin/env python3
"""
The shared "ask" orchestrator: question -> config -> run -> explanation.

Both the sim_ask CLI and the web /api/ask endpoint call answer_question(), so
the natural-language pipeline lives in exactly one place.
"""

from kernel import DomainConfig, run_monte_carlo, evaluate_safety, compute_fitness
from mcp_server import _generate_narrative

from .compiler import compile_config
from .explain import explain_results


def run_config(config, *, seed=42, n_simulations=None):
    """Run a validated config and assemble a /api/simulate-shaped result dict."""
    cfg = DomainConfig.from_dict(config)
    mc = run_monte_carlo(cfg, seed=seed, n_override=n_simulations)
    safety = evaluate_safety(mc, cfg.safety) if cfg.safety else {}
    fitness = compute_fitness(mc, cfg.fitness, cfg.safety) if cfg.fitness else 0
    narrative = _generate_narrative(mc["stats"], safety)
    return {
        "domain": mc["domain"],
        "n_simulations": mc["n_simulations"],
        "stats": mc["stats"],
        "trajectories": mc["trajectories"],
        "safety": safety,
        "fitness": fitness,
        "narrative": narrative,
    }


def answer_question(question, *, n_simulations=None, seed=42, max_repairs=3,
                    backend=None, model=None, _complete=None):
    """Compile a question to a config, run it, and explain the result.

    Returns {valid, config, attempts, errors, results, explanation}. When the
    config never validates, results/explanation are None and errors say why.
    """
    comp = compile_config(question, n_simulations=n_simulations, max_repairs=max_repairs,
                          backend=backend, model=model, _complete=_complete)
    if not comp["valid"]:
        return {
            "valid": False,
            "config": comp["config"],
            "attempts": comp["attempts"],
            "errors": comp["errors"],
            "results": None,
            "explanation": None,
        }

    config = comp["config"]
    results = run_config(config, seed=seed, n_simulations=n_simulations)
    explanation = explain_results(question, results, backend=backend, model=model, _complete=_complete)
    return {
        "valid": True,
        "config": config,
        "attempts": comp["attempts"],
        "errors": [],
        "results": results,
        "explanation": explanation,
    }

#!/usr/bin/env python3
"""Deterministic baseline must use the MODE of a Bernoulli, not its mean.

The baseline plugged the Bernoulli probability p in as a fixed point estimate,
so a hit*1000 payout with p=0.3 produced a baseline payout of 300 — an outcome
that can never occur (the indicator is 0 or 1, never 0.3). The point estimate
should be the realizable mode: 1 if p>=0.5 else 0.
"""
import os
import sys
import copy
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import kernel
import diagnostics


def _bern_config(p):
    return {
        "name": "bern", "n_simulations": 100, "n_steps": 1, "seed": 3,
        "parameters": {"hit": {"distribution": "bernoulli", "params": {"p": p}}},
        "controls": {}, "exogenous": {},
        "initial_state": {"total": 0},
        "step_logic": [{"target": "payout", "expr": "hit * 1000"}],
        "accumulators": {"total": "total + payout"},
        "metrics": {"payout": {"expr": "payout"}},
    }


class TestDeterministicBaselineBernoulli(unittest.TestCase):
    def test_low_p_uses_zero_mode(self):
        cfg = kernel.DomainConfig.from_dict(_bern_config(0.3))
        base = diagnostics.deterministic_baseline(cfg)
        self.assertEqual(base["final_metrics"]["payout"], 0.0)

    def test_high_p_uses_one_mode(self):
        cfg = kernel.DomainConfig.from_dict(_bern_config(0.7))
        base = diagnostics.deterministic_baseline(cfg)
        self.assertEqual(base["final_metrics"]["payout"], 1000.0)


if __name__ == "__main__":
    unittest.main()

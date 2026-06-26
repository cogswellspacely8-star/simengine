#!/usr/bin/env python3
"""Sensitivity analysis must use common random numbers (CRN).

The central-difference used different seeds for the up and down legs, so
up_mean - dn_mean carried raw Monte Carlo sampling noise. A variable with zero
effect on the metric therefore registered a spurious nonzero impact. Sharing one
seed per trial isolates the parameter effect.
"""
import os
import sys
import copy
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import kernel
import diagnostics

SENS_CONFIG = {
    "name": "sens", "n_simulations": 200, "n_steps": 1, "seed": 7,
    "parameters": {
        "driver": {"distribution": "normal", "params": {"mean": 10, "std": 2}},
        "unused": {"distribution": "normal", "params": {"mean": 5, "std": 2}},
    },
    "controls": {}, "exogenous": {},
    "initial_state": {"total": 0},
    "step_logic": [{"target": "out", "expr": "driver"}],
    "accumulators": {"total": "total + out"},
    "metrics": {"total": {"expr": "total"}},
}


class TestSensitivityCRN(unittest.TestCase):
    def test_zero_effect_variable_scores_near_zero(self):
        cfg = kernel.DomainConfig.from_dict(copy.deepcopy(SENS_CONFIG))
        res = diagnostics.sensitivity_analysis(cfg, n_base=200, n_perturb=10, seed=7)
        items = {(s["variable"], s["parameter"]): s for s in res["sensitivities"]}
        unused = items[("unused", "mean")]
        self.assertLess(
            unused["avg_impact_on_mean"], 0.05,
            f"a variable with no effect on the metric should score ~0 impact, "
            f"got {unused['avg_impact_on_mean']}")

    def test_real_driver_still_registers_impact(self):
        cfg = kernel.DomainConfig.from_dict(copy.deepcopy(SENS_CONFIG))
        res = diagnostics.sensitivity_analysis(cfg, n_base=200, n_perturb=10, seed=7)
        items = {(s["variable"], s["parameter"]): s for s in res["sensitivities"]}
        self.assertGreater(items[("driver", "mean")]["avg_impact_on_mean"], 0.5)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Integer-valued optimizer controls.

The optimizer mutated every tunable as a continuous real, so it would recommend
"1.5 baristas" or "2.88 doctors" — physically impossible. A tunable may opt in
with "integer": true (or a numeric "step") and the optimizer must quantize it.
"""
import os
import sys
import copy
import random
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import kernel

BASE = {
    "name": "int test", "n_simulations": 50, "n_steps": 2, "seed": 1,
    "parameters": {},
    "controls": {"baristas": {"distribution": "fixed", "params": {"value": 2}}},
    "exogenous": {},
    "initial_state": {"profit": 0},
    "step_logic": [{"target": "daily", "expr": "baristas * 10"}],
    "accumulators": {"profit": "profit + daily"},
    "metrics": {"profit": {"expr": "profit", "format": "dollar"}},
    "fitness": {"components": [{"expr": "profit_median", "weight": 1.0}]},
    "tunable": [{"path": "controls.baristas.params.value", "range": [1, 6], "integer": True}],
}


class TestIntegerControls(unittest.TestCase):
    def setUp(self):
        kernel.clear_tunable_cache()
        random.seed(0)

    def test_mutate_respects_integer_flag(self):
        cfg = copy.deepcopy(BASE)
        for _ in range(100):
            m = kernel.mutate_config(cfg, BASE["tunable"], rate=1.0, strength=0.5)
            v = m["controls"]["baristas"]["params"]["value"]
            self.assertEqual(v, int(v), f"{v} is not integral")
            self.assertGreaterEqual(v, 1)
            self.assertLessEqual(v, 6)

    def test_evolve_integer_control_never_fractional(self):
        result = kernel.evolve(copy.deepcopy(BASE), generations=2, population=4,
                               workers=1, verbose=False)
        v = result["best_controls"]["controls.baristas.params.value"]
        self.assertEqual(v, int(v), f"optimizer returned fractional control {v}")

    def test_step_quantization(self):
        kernel.clear_tunable_cache()
        tun = [{"path": "controls.baristas.params.value", "range": [0, 10], "step": 0.5}]
        cfg = copy.deepcopy(BASE)
        for _ in range(100):
            m = kernel.mutate_config(cfg, tun, rate=1.0, strength=0.5)
            v = m["controls"]["baristas"]["params"]["value"]
            self.assertAlmostEqual(round(v / 0.5) * 0.5, v, places=6,
                                   msg=f"{v} not on a 0.5 step")

    def test_base_seed_is_quantized(self):
        # An off-grid integer seed must not survive as best_controls when the
        # unmutated base wins (population=1 evaluates only the seed).
        cfg = copy.deepcopy(BASE)
        cfg["controls"]["baristas"]["params"]["value"] = 2.5
        result = kernel.evolve(cfg, generations=1, population=1, workers=1, verbose=False)
        v = result["best_controls"]["controls.baristas.params.value"]
        self.assertEqual(v, int(v), f"off-grid base seed survived as {v}")

    def test_without_flag_stays_continuous(self):
        kernel.clear_tunable_cache()
        tun = [{"path": "controls.baristas.params.value", "range": [1, 6]}]
        cfg = copy.deepcopy(BASE)
        seen_fractional = False
        for _ in range(100):
            m = kernel.mutate_config(cfg, tun, rate=1.0, strength=0.5)
            v = m["controls"]["baristas"]["params"]["value"]
            if v != int(v):
                seen_fractional = True
                break
        self.assertTrue(seen_fractional, "a tunable without the integer flag must stay continuous")


if __name__ == "__main__":
    unittest.main()

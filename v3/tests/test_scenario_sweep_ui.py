#!/usr/bin/env python3
"""
Static-contract tests for the scenario-sweep UI (single-file vanilla SPA).

The sweep logic runs only in the browser, so these tests pin the contract the
design spec requires (docs/superpowers/specs/2026-06-28-scenario-sweep-design.md)
by reading index.html as text — same approach as test_static_ui_layout.py.
"""

import os
import re
import sys
import unittest

INDEX = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")


class TestScenarioSweepContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX) as f:
            cls.html = f.read()

    def _fn_body(self, name):
        """Source between `function <name>(` and the next top-level function."""
        m = re.search(rf"function {name}\(.*?(?=\nfunction |\n// ═)", self.html,
                      re.DOTALL)
        self.assertIsNotNone(m, f"function {name} not found")
        return m.group(0)

    def test_sweep_button_present(self):
        self.assertIn('id="btn-sweep"', self.html)
        self.assertIn('onclick="openSweep()"', self.html)

    def test_core_functions_exist(self):
        for fn in ("sweepValues", "captureInputs", "openSweep", "runSweep",
                   "updateSweepPreview"):
            self.assertIn(f"function {fn}(", self.html)

    def test_sweep_max_cap_declared_and_enforced(self):
        self.assertIn("const SWEEP_MAX = 12", self.html)
        body = self._fn_body("runSweep")
        self.assertIn("SWEEP_MAX", body)

    def test_sweep_values_uses_float_epsilon(self):
        body = self._fn_body("sweepValues")
        self.assertIn("1e-9", body)   # inclusive-endpoint epsilon
        self.assertIn("1e6", body)    # drift-rounding

    def test_scenarios_carry_input_snapshots(self):
        save = self._fn_body("saveScenario")
        self.assertIn("inputs: captureInputs()", save)
        sweep = self._fn_body("runSweep")
        self.assertIn("inputs:", sweep)
        self.assertIn("swept: true", sweep)

    def test_compare_renders_input_diff_and_uses_setmain(self):
        body = self._fn_body("compareScenarios")
        self.assertIn("Inputs That Differ", body)
        self.assertIn("_sweepPath", body)
        # Regression guard for the folded-in P2 fix: no raw innerHTML write.
        self.assertIn("setMain(html)", body)
        self.assertNotIn("main.innerHTML = html", body)
        # The histogram redraw must survive the setMain switch.
        self.assertIn("drawCompareHistograms", body)

    def test_sweep_overrides_ride_the_existing_simulate_path(self):
        body = self._fn_body("runSweep")
        self.assertIn("collectOverrides()", body)
        self.assertIn("/api/simulate", body)


if __name__ == "__main__":
    unittest.main()

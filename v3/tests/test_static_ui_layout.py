#!/usr/bin/env python3
"""Static-contract guards for the single-file UI (no browser harness).

These pin the P2 fixes against silent regression: the grid scroll-ownership fix
(results were rendering off-screen), the centralized scroll-resetting writer, the
abortable /api/ask call, and the optimizer's recommended-settings output.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

HTML = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'index.html')).read()


class TestStaticUiLayout(unittest.TestCase):
    def test_app_uses_fixed_height_not_min_height(self):
        # min-height let a tall sidebar grow the document and push results off-screen.
        self.assertIn("height: calc(100vh - 45px)", HTML)
        self.assertNotIn("min-height: calc(100vh - 45px)", HTML)

    def test_scroll_containers_declare_min_height_zero(self):
        # .sidebar and .main both need min-height:0 so overflow-y engages in the grid.
        self.assertGreaterEqual(HTML.count("min-height: 0"), 2)

    def test_results_writes_route_through_setMain_with_scroll_reset(self):
        self.assertIn("function setMain(", HTML)
        self.assertIn("m.scrollTop = 0", HTML)

    def test_no_raw_main_innerHTML_writes_remain(self):
        # every results write must go through setMain (which resets scroll).
        self.assertNotIn("getElementById('main').innerHTML =", HTML)

    def test_ask_is_abortable(self):
        self.assertIn("AbortController", HTML)
        self.assertIn("signal: ctrl.signal", HTML)

    def test_evolve_shows_recommended_settings(self):
        self.assertIn("Recommended Settings", HTML)


if __name__ == "__main__":
    unittest.main()

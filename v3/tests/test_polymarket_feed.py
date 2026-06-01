#!/usr/bin/env python3
"""
Tests for the opt-in Polymarket Gamma feed adapter (feeds/polymarket.py).
Pure stdlib unittest. The network call is isolated behind an injectable seam,
so these tests never touch the network.
"""

import os
import sys
import math
import unittest

# Make v3 package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from feeds import polymarket

# Gamma returns outcomes/outcomePrices as JSON-encoded strings.
SAMPLE_MARKET = {
    "question": "Will it rain in NYC tomorrow?",
    "slug": "will-it-rain-nyc-tomorrow",
    "outcomes": '["Yes", "No"]',
    "outcomePrices": '["0.62", "0.38"]',
    "active": True,
    "closed": False,
}

# Some responses already give native arrays.
SAMPLE_MARKET_NATIVE = {
    "question": "Native arrays?",
    "outcomes": ["Yes", "No"],
    "outcomePrices": [0.7, 0.3],
}


class TestParsing(unittest.TestCase):
    def test_implied_probabilities_from_json_strings(self):
        probs = polymarket.implied_probabilities(SAMPLE_MARKET)
        self.assertAlmostEqual(probs["Yes"], 0.62)
        self.assertAlmostEqual(probs["No"], 0.38)

    def test_implied_probabilities_from_native_lists(self):
        probs = polymarket.implied_probabilities(SAMPLE_MARKET_NATIVE)
        self.assertAlmostEqual(probs["Yes"], 0.7)
        self.assertAlmostEqual(probs["No"], 0.3)

    def test_yes_probability_matches_case_insensitively(self):
        self.assertAlmostEqual(polymarket.yes_probability(SAMPLE_MARKET), 0.62)

    def test_yes_probability_falls_back_to_first_outcome(self):
        market = {"outcomes": '["Trump", "Biden"]',
                  "outcomePrices": '["0.55", "0.45"]'}
        self.assertAlmostEqual(polymarket.yes_probability(market), 0.55)


class TestBetaPrior(unittest.TestCase):
    def test_beta_prior_balanced_at_half(self):
        prior = polymarket.beta_prior(0.5, strength=20)
        self.assertAlmostEqual(prior["alpha"], 10.0)
        self.assertAlmostEqual(prior["beta"], 10.0)

    def test_beta_prior_concentration(self):
        prior = polymarket.beta_prior(0.62, strength=20)
        self.assertAlmostEqual(prior["alpha"], 12.4)
        self.assertAlmostEqual(prior["beta"], 7.6)

    def test_beta_prior_rejects_out_of_range_probability(self):
        with self.assertRaises(ValueError):
            polymarket.beta_prior(1.5, strength=20)

    def test_beta_prior_rejects_nonpositive_strength(self):
        with self.assertRaises(ValueError):
            polymarket.beta_prior(0.5, strength=0)


class TestPriorVariable(unittest.TestCase):
    def test_prior_variable_is_triangular_centered_on_probability(self):
        var = polymarket.prior_variable(0.5, strength=20)
        self.assertEqual(var["distribution"], "triangular")
        self.assertAlmostEqual(var["params"]["mode"], 0.5)
        self.assertLess(var["params"]["low"], 0.5)
        self.assertGreater(var["params"]["high"], 0.5)

    def test_prior_variable_bounds_stay_in_unit_interval(self):
        var = polymarket.prior_variable(0.95, strength=20)
        self.assertGreaterEqual(var["params"]["low"], 0.0)
        self.assertLessEqual(var["params"]["high"], 1.0)

    def test_prior_variable_is_updatable_via_beta_binomial(self):
        var = polymarket.prior_variable(0.62, strength=20)
        self.assertEqual(var["calibration"]["update_method"], "beta_binomial")

    def test_market_prior_from_raw_market(self):
        var = polymarket.market_prior(SAMPLE_MARKET, strength=20)
        self.assertAlmostEqual(var["params"]["mode"], 0.62)


class TestFetch(unittest.TestCase):
    def test_fetch_markets_uses_injected_getter(self):
        captured = {}

        def fake_get(url):
            captured["url"] = url
            return [SAMPLE_MARKET]

        result = polymarket.fetch_markets(limit=5, _get=fake_get)
        self.assertEqual(result, [SAMPLE_MARKET])
        self.assertIn("gamma-api.polymarket.com/markets", captured["url"])
        self.assertIn("limit=5", captured["url"])


if __name__ == "__main__":
    unittest.main()

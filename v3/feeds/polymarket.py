#!/usr/bin/env python3
"""
Polymarket Gamma feed adapter (OPT-IN).
=======================================
Turns a live Polymarket prediction-market price into a SimEngine prior you can
drop into a domain config and refine with the Beta-Binomial updater.

This module is OPT-IN and lives outside the core engine on purpose:
  - It is the only part of SimEngine that reaches the network.
  - It still uses ONLY the Python standard library (urllib) — no new deps.
  - The core engine never imports it; nothing here changes the stdlib promise.

ToS / posture: market prices are treated as INTERNAL simulation inputs feeding a
derived analytical prior. This is not a rebroadcast price feed and it emits no
trade signal. Keep it that way.

Gamma API base: https://gamma-api.polymarket.com
"""

import json
import math

GAMMA_BASE = "https://gamma-api.polymarket.com"


def _as_list(value):
    """Gamma returns outcomes/outcomePrices as JSON-encoded strings or lists."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def implied_probabilities(market):
    """Map a Gamma market dict to {outcome_label: implied_probability}."""
    outcomes = _as_list(market.get("outcomes", []))
    prices = _as_list(market.get("outcomePrices", []))
    return {str(o): float(p) for o, p in zip(outcomes, prices)}


def yes_probability(market):
    """The market-implied probability of the 'Yes' outcome.

    Falls back to the first outcome when there is no outcome named 'Yes'.
    """
    probs = implied_probabilities(market)
    if not probs:
        raise ValueError("market has no outcomes/outcomePrices")
    for label, p in probs.items():
        if label.strip().lower() == "yes":
            return p
    return next(iter(probs.values()))


def beta_prior(probability, strength=20):
    """Beta(alpha, beta) prior with mean=probability and concentration=strength.

    Method of moments: alpha = p * s, beta = (1 - p) * s.
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    if strength <= 0:
        raise ValueError("strength must be positive")
    return {"alpha": probability * strength, "beta": (1.0 - probability) * strength}


def prior_variable(probability, strength=20, distribution="triangular"):
    """Build a SimEngine variable_def from a market probability.

    distribution="triangular" (default, the historical contract): bounds come
    from the implied Beta's spread; updates go through the moment-matched
    Beta-Binomial path.

    distribution="beta": the variable IS Beta(p*strength, (1-p)*strength), so
    Beta-Binomial updates are exact and the prior strength is literally the
    pseudo-count. Prefer this for anything that will be re-updated repeatedly
    (e.g. a market prior refined as resolutions arrive).
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    if strength <= 0:
        raise ValueError("strength must be positive")
    if distribution == "beta":
        ab = beta_prior(probability, strength)
        return {
            "distribution": "beta",
            "params": {"alpha": round(ab["alpha"], 4), "beta": round(ab["beta"], 4)},
            "calibration": {
                "source": f"Polymarket-implied probability {probability:.2f} "
                          f"(Beta prior, strength {strength})",
                "updatable": True,
                "update_method": "beta_binomial",
                "prior_strength": strength,
            },
        }
    if distribution != "triangular":
        raise ValueError("distribution must be 'triangular' or 'beta'")
    std = math.sqrt(probability * (1.0 - probability) / (strength + 1.0))
    low = max(0.0, probability - 2.0 * std)
    high = min(1.0, probability + 2.0 * std)
    return {
        "distribution": "triangular",
        "params": {
            "low": round(low, 4),
            "mode": round(probability, 4),
            "high": round(high, 4),
        },
        "calibration": {
            "source": f"Polymarket-implied probability {probability:.2f} "
                      f"(Beta prior, strength {strength})",
            "updatable": True,
            "update_method": "beta_binomial",
            # Carried into bayesian.update_parameter as the Beta pseudo-count,
            # so the market's weight survives into the posterior.
            "prior_strength": strength,
        },
    }


def market_prior(market, strength=20, distribution="triangular"):
    """Convenience: raw Gamma market dict -> SimEngine prior variable_def."""
    return prior_variable(yes_probability(market), strength=strength,
                          distribution=distribution)


def _http_get_json(url):
    """Default network getter (stdlib urllib). Isolated so tests can inject."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "simengine-feed/3.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_markets(query=None, *, active=True, closed=False, limit=20, _get=None):
    """Fetch markets from the Polymarket Gamma API.

    Network call. Pass `_get` to inject a getter (used in tests). Returns the
    raw list of market dicts; pair with implied_probabilities / market_prior.
    """
    import urllib.parse
    get = _get or _http_get_json
    params = {"limit": limit, "active": str(active).lower(),
              "closed": str(closed).lower()}
    if query:
        params["query"] = query
    url = f"{GAMMA_BASE}/markets?" + urllib.parse.urlencode(params)
    return get(url)

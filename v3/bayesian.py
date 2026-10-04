"""
SimEngine Bayesian Updating Module
====================================
Conjugate prior updates for calibrating simulation parameters
from observed data. No external dependencies.

Supported update methods:
  - Beta-Binomial:   for rates/probabilities (close_rate, churn_rate)
  - Gamma-Poisson:   for counts (leads_per_month, bugs_per_sprint)
  - Normal-Normal:   for means (project_value, salary)

Usage:
    from bayesian import update_parameter

    updated = update_parameter(
        variable_def={"distribution": "triangular", "params": {"low": 0.1, "mode": 0.3, "high": 0.5}},
        observations=[0.25, 0.30, 0.28, 0.35, 0.22],
        method="beta_binomial"  # or inferred from calibration.update_method
    )
"""

import math
import statistics
import copy


def _not_updatable(prior_params, method):
    """Uniform / categorical / empirical / process params have no conjugate
    mapping. Return the params unchanged with a skipped report. (Returning the
    bare dict, as before, made update_config unpack its KEYS into the config:
    params became the string 'low'.)"""
    return prior_params, {
        "skipped": True, "method": method,
        "reason": f"no conjugate mapping for params {sorted(prior_params)}; "
                  f"params left unchanged",
    }


def beta_binomial_update(prior_params, observations, n_pseudo=10):
    """
    Update a rate/probability parameter using Beta-Binomial conjugate.

    observations: list of (successes, trials) tuples, OR list of observed rates
    prior_params: dict with low/mode/high (triangular) or mean/std (normal)

    Returns updated params dict.
    """
    # Exact path: the variable IS a Beta(alpha, beta) (optionally rescaled to
    # [low, high]). Conjugate update keeps it a Beta — no mapping back into a
    # triangular, no pseudo-count guess.
    if "alpha" in prior_params and "beta" in prior_params:
        return _beta_exact_update(prior_params, observations)

    # Extract prior from triangular or uniform params
    if "mode" in prior_params:
        prior_mean = prior_params["mode"]
        prior_low = prior_params.get("low", 0)
        prior_high = prior_params.get("high", 1)
    elif "mean" in prior_params:
        prior_mean = prior_params["mean"]
        prior_low = prior_params.get("min", 0)
        prior_high = prior_params.get("max", 1)
    elif "value" in prior_params:
        prior_mean = prior_params["value"]
        prior_low, prior_high = 0, 1
    else:
        return _not_updatable(prior_params, "beta_binomial")

    # Convert prior mean to Beta parameters by method of moments. n_pseudo is
    # the prior's concentration in pseudo-observations (default 10; callers
    # that built the prior with a known strength pass it through).
    # No floor at 1: flooring alpha/beta shifted the prior mean (a mode of 0.05
    # with n_pseudo=10 became Beta(1, 9.5), prior mean 0.095). Only guard
    # against a degenerate zero-mass prior so the posterior stays proper.
    prior_mean = min(max(prior_mean, 1e-9), 1 - 1e-9)
    alpha_prior = max(1e-6, prior_mean * n_pseudo)
    beta_prior = max(1e-6, (1 - prior_mean) * n_pseudo)

    # Process observations
    total_successes, total_trials = _count_observations(observations)

    # Posterior
    alpha_post = alpha_prior + total_successes
    beta_post = beta_prior + (total_trials - total_successes)

    # Posterior statistics
    post_mean = alpha_post / (alpha_post + beta_post)
    post_var = (alpha_post * beta_post) / ((alpha_post + beta_post) ** 2 * (alpha_post + beta_post + 1))
    post_std = math.sqrt(post_var)

    # Map back to triangular params
    new_mode = max(prior_low, min(prior_high, post_mean))
    new_low = max(0, post_mean - 2 * post_std)
    new_high = min(1, post_mean + 2 * post_std)

    result = copy.deepcopy(prior_params)
    if "mode" in result:
        result["mode"] = round(new_mode, 4)
        result["low"] = round(max(result.get("low", 0) * 0.5, new_low), 4)
        result["high"] = round(min(result.get("high", 1) * 1.5, new_high), 4)
    elif "mean" in result:
        result["mean"] = round(post_mean, 4)
        result["std"] = round(post_std, 4)
    elif "value" in result:
        result["value"] = round(post_mean, 4)

    return result, {
        "method": "beta_binomial",
        "alpha_prior": round(alpha_prior, 2),
        "beta_prior": round(beta_prior, 2),
        "alpha_posterior": round(alpha_post, 2),
        "beta_posterior": round(beta_post, 2),
        "prior_mean": round(prior_mean, 4),
        "posterior_mean": round(post_mean, 4),
        "posterior_std": round(post_std, 4),
        "observations_used": len(observations),
        "total_trials": total_trials,
        "credible_interval_90": [
            round(max(0, post_mean - 1.645 * post_std), 4),
            round(min(1, post_mean + 1.645 * post_std), 4),
        ],
    }


def _count_observations(observations):
    """(successes, trials) from a list of (s, n) tuples or of observed rates."""
    total_successes = 0
    total_trials = 0
    if observations and isinstance(observations[0], (list, tuple)):
        for s, n in observations:
            total_successes += s
            total_trials += n
    else:
        # Observed rates: treat each as ~20 trials (documented approximation;
        # pass (successes, trials) tuples for exact counts).
        trials_per_obs = 20
        for rate in observations:
            total_successes += rate * trials_per_obs
            total_trials += trials_per_obs
    return total_successes, total_trials


def _beta_exact_update(prior_params, observations):
    alpha_prior = float(prior_params["alpha"])
    beta_prior = float(prior_params["beta"])
    successes, trials = _count_observations(observations)
    alpha_post = alpha_prior + successes
    beta_post = beta_prior + (trials - successes)
    post_mean = alpha_post / (alpha_post + beta_post)
    post_var = (alpha_post * beta_post) / ((alpha_post + beta_post) ** 2 * (alpha_post + beta_post + 1))
    post_std = math.sqrt(post_var)
    result = copy.deepcopy(prior_params)
    result["alpha"] = round(alpha_post, 4)
    result["beta"] = round(beta_post, 4)
    return result, {
        "method": "beta_binomial",
        "exact": True,
        "alpha_prior": round(alpha_prior, 2),
        "beta_prior": round(beta_prior, 2),
        "alpha_posterior": round(alpha_post, 2),
        "beta_posterior": round(beta_post, 2),
        "prior_mean": round(alpha_prior / (alpha_prior + beta_prior), 4),
        "posterior_mean": round(post_mean, 4),
        "posterior_std": round(post_std, 4),
        "observations_used": len(observations),
        "total_trials": trials,
        "credible_interval_90": [
            round(max(0, post_mean - 1.645 * post_std), 4),
            round(min(1, post_mean + 1.645 * post_std), 4),
        ],
    }


def _gamma_exact_update(prior_params, observations):
    shape_prior = float(prior_params["shape"])
    rate_prior = float(prior_params["rate"]) if "rate" in prior_params else 1.0 / float(prior_params["scale"])
    n = len(observations)
    total = sum(observations)
    shape_post = shape_prior + total
    rate_post = rate_prior + n
    post_mean = shape_post / rate_post
    post_std = math.sqrt(shape_post) / rate_post
    result = copy.deepcopy(prior_params)
    result["shape"] = round(shape_post, 4)
    if "rate" in result:
        result["rate"] = round(rate_post, 4)
    else:
        result["scale"] = round(1.0 / rate_post, 6)
    return result, {
        "method": "gamma_poisson",
        "exact": True,
        "alpha_prior": round(shape_prior, 2),
        "beta_prior": round(rate_prior, 2),
        "alpha_posterior": round(shape_post, 2),
        "beta_posterior": round(rate_post, 2),
        "prior_mean": round(shape_prior / rate_prior, 4),
        "posterior_mean": round(post_mean, 4),
        "posterior_std": round(post_std, 4),
        "observations_used": n,
        "credible_interval_90": [
            round(max(0, post_mean - 1.645 * post_std), 4),
            round(post_mean + 1.645 * post_std, 4),
        ],
    }


def gamma_poisson_update(prior_params, observations, n_pseudo=5):
    """
    Update a count parameter using Gamma-Poisson conjugate.

    observations: list of observed counts
    prior_params: dict with shape+scale/rate (exact), or low/mode/high,
                  lambda, value (moment-matched prior with n_pseudo)
    """
    if "shape" in prior_params and ("scale" in prior_params or "rate" in prior_params):
        return _gamma_exact_update(prior_params, observations)

    if "mode" in prior_params:
        prior_mean = prior_params["mode"]
    elif "lambda" in prior_params:
        prior_mean = prior_params["lambda"]
    elif "value" in prior_params:
        prior_mean = prior_params["value"]
    elif "mean" in prior_params:
        prior_mean = prior_params["mean"]
    else:
        return _not_updatable(prior_params, "gamma_poisson")

    # Gamma prior: shape=alpha, rate=beta. Mean = alpha/beta. n_pseudo is the
    # prior's concentration in pseudo-observations (default 5).
    # No floor at 1 (it shifted the prior mean for rates below 1/n_pseudo).
    alpha_prior = max(1e-6, prior_mean * n_pseudo)
    beta_prior = n_pseudo

    # Update
    n = len(observations)
    total = sum(observations)
    alpha_post = alpha_prior + total
    beta_post = beta_prior + n

    post_mean = alpha_post / beta_post
    post_var = alpha_post / (beta_post ** 2)
    post_std = math.sqrt(post_var)

    result = copy.deepcopy(prior_params)
    if "mode" in result:
        result["mode"] = round(post_mean, 2)
        result["low"] = round(max(0, post_mean - 2 * post_std), 2)
        result["high"] = round(post_mean + 2 * post_std, 2)
    elif "lambda" in result:
        result["lambda"] = round(post_mean, 2)
    elif "value" in result:
        result["value"] = round(post_mean, 2)
    elif "mean" in result:
        result["mean"] = round(post_mean, 2)
        result["std"] = round(post_std, 2)

    return result, {
        "method": "gamma_poisson",
        "alpha_prior": round(alpha_prior, 2),
        "beta_prior": round(beta_prior, 2),
        "alpha_posterior": round(alpha_post, 2),
        "beta_posterior": round(beta_post, 2),
        "prior_mean": round(prior_mean, 4),
        "posterior_mean": round(post_mean, 4),
        "posterior_std": round(post_std, 4),
        "observations_used": n,
        "credible_interval_90": [
            round(max(0, post_mean - 1.645 * post_std), 2),
            round(post_mean + 1.645 * post_std, 2),
        ],
    }


def normal_normal_update(prior_params, observations):
    """
    Update a continuous parameter using Normal-Normal conjugate.

    observations: list of observed values
    prior_params: dict with mean/std or median/spread or value
    """
    if "median" in prior_params:
        prior_mean = prior_params["median"]
        prior_std = prior_params.get("spread", 1) * prior_mean * 0.5
    elif "mean" in prior_params:
        prior_mean = prior_params["mean"]
        prior_std = prior_params.get("std", abs(prior_mean) * 0.3 or 1)
    elif "mode" in prior_params:
        prior_mean = prior_params["mode"]
        rng = prior_params.get("high", prior_mean * 2) - prior_params.get("low", 0)
        prior_std = rng / 4
    elif "value" in prior_params:
        prior_mean = prior_params["value"]
        prior_std = abs(prior_mean) * 0.2 or 1
    else:
        return _not_updatable(prior_params, "normal_normal")

    prior_var = prior_std ** 2

    n = len(observations)
    obs_mean = statistics.mean(observations)
    obs_var = statistics.variance(observations) if n > 1 else prior_var

    # Normal-Normal conjugate update
    post_var = 1 / (1 / prior_var + n / obs_var)
    post_mean = post_var * (prior_mean / prior_var + n * obs_mean / obs_var)
    post_std = math.sqrt(post_var)

    result = copy.deepcopy(prior_params)
    if "median" in result:
        result["median"] = round(post_mean, 2)
    elif "mean" in result:
        result["mean"] = round(post_mean, 4)
        result["std"] = round(post_std, 4)
    elif "mode" in result:
        result["mode"] = round(post_mean, 2)
        result["low"] = round(max(result.get("low", 0), post_mean - 2 * post_std), 2)
        result["high"] = round(min(result.get("high", post_mean * 3), post_mean + 2 * post_std), 2)
    elif "value" in result:
        result["value"] = round(post_mean, 2)

    return result, {
        "method": "normal_normal",
        "prior_mean": round(prior_mean, 4),
        "prior_std": round(prior_std, 4),
        "posterior_mean": round(post_mean, 4),
        "posterior_std": round(post_std, 4),
        "observations_used": n,
        "observed_mean": round(obs_mean, 4),
        "credible_interval_90": [
            round(post_mean - 1.645 * post_std, 4),
            round(post_mean + 1.645 * post_std, 4),
        ],
    }


# Method dispatch
UPDATERS = {
    "beta_binomial": beta_binomial_update,
    "Beta-Binomial conjugate": beta_binomial_update,
    "Beta-Binomial conjugate after observing actual conversions": beta_binomial_update,
    "Beta-Binomial conjugate after observing actual closes/leads per month": beta_binomial_update,
    "Bayesian conjugate (Beta-Binomial) after observing actual closes/leads per month": beta_binomial_update,
    "gamma_poisson": gamma_poisson_update,
    "Gamma-Poisson": gamma_poisson_update,
    "Poisson conjugate (Gamma-Poisson) after observing actual monthly lead counts": gamma_poisson_update,
    "normal_normal": normal_normal_update,
    "Normal conjugate": normal_normal_update,
    "Normal conjugate after observing actual sprint velocities": normal_normal_update,
}


def infer_method(variable_def):
    """Infer the best update method from the variable definition."""
    cal = variable_def.get("calibration", {})
    method_str = cal.get("update_method", "")

    # Check explicit mapping
    for key, fn in UPDATERS.items():
        if key.lower() in method_str.lower():
            return fn

    # Infer from distribution type and value range
    dist = variable_def.get("distribution", "")
    params = variable_def.get("params", {})

    if dist in ("bernoulli", "beta"):
        return beta_binomial_update
    if dist == "gamma":
        return gamma_poisson_update

    # If values are between 0 and 1, probably a rate
    vals = [v for v in params.values() if isinstance(v, (int, float))]
    if vals and all(0 <= v <= 1 for v in vals):
        return beta_binomial_update

    # If distribution is poisson or values are small integers
    if dist == "poisson":
        return gamma_poisson_update
    if vals and all(v == int(v) and v < 100 for v in vals):
        return gamma_poisson_update

    return normal_normal_update


def update_parameter(variable_def, observations, method=None):
    """
    Update a single variable definition with observed data.

    Args:
        variable_def: dict with distribution, params, calibration
        observations: list of observed values
        method: 'beta_binomial', 'gamma_poisson', 'normal_normal', or None (auto)

    Returns:
        (updated_params, diagnostics)
    """
    if not observations:
        return variable_def["params"], {"error": "no observations"}

    if method and method in UPDATERS:
        updater = UPDATERS[method]
    else:
        updater = infer_method(variable_def)

    # Prior concentration (pseudo-observations) declared on the variable, e.g.
    # by feeds/polymarket.prior_variable(strength=...). Without this the
    # updater's default pseudo-count silently overrode whatever strength the
    # prior was built with, so `strength` was decorative.
    cal = variable_def.get("calibration") or {}
    strength = cal.get("prior_strength")
    if strength is not None and updater in (beta_binomial_update, gamma_poisson_update):
        strength = float(strength)
        if strength <= 0:
            raise ValueError("calibration.prior_strength must be positive")
        result = updater(variable_def["params"], observations, n_pseudo=strength)
    else:
        result = updater(variable_def["params"], observations)
    # Defensive: an updater must return (params, report).
    if not (isinstance(result, tuple) and len(result) == 2):
        return variable_def["params"], {"skipped": True, "reason": "updater returned no report"}
    return result


def update_config(config_data, observation_data):
    """
    Update all updatable parameters in a config with observed data.

    Args:
        config_data: full domain config dict
        observation_data: dict of {variable_name: [observed_values]}

    Returns:
        (updated_config, update_report)
    """
    updated = copy.deepcopy(config_data)
    report = {}

    for cat in ("parameters", "controls", "exogenous", "variables"):
        section = updated.get(cat, {})
        for vname, vdef in section.items():
            if vname not in observation_data:
                continue

            cal = vdef.get("calibration", {})
            if cal.get("updatable") is False:
                report[vname] = {"skipped": True, "reason": "not updatable"}
                continue

            obs = observation_data[vname]
            new_params, diagnostics = update_parameter(vdef, obs)
            section[vname]["params"] = new_params
            report[vname] = diagnostics

    return updated, report

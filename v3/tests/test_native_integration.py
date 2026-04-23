#!/usr/bin/env python3
"""
Tests for the optional native backend integration.
"""

import copy
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kernel
import native
import diagnostics
import server


MINI_CONFIG = {
    "name": "Native Test Domain",
    "n_simulations": 50,
    "n_steps": 3,
    "step_label": "month",
    "seed": 42,
    "parameters": {
        "rate": {"distribution": "triangular", "params": {"low": 0.1, "mode": 0.3, "high": 0.5}}
    },
    "controls": {},
    "exogenous": {},
    "initial_state": {"total": 0},
    "step_logic": [
        {"target": "income", "expr": "rate * 1000"}
    ],
    "accumulators": {"total": "total + income"},
    "metrics": {
        "final_total": {"expr": "total", "format": "dollar"}
    },
    "safety": {
        "chance_constraints": [{"metric": "final_total", "condition": "below", "threshold": 500, "max_prob": 0.20}],
        "cvar_constraints": []
    },
    "fitness": {"components": [{"expr": "final_total_median / 10", "weight": 1.0}]},
    "tunable": [{"path": "parameters.rate.params.mode", "range": [0.1, 0.5]}]
}


def _cfg():
    return kernel.DomainConfig.from_dict(copy.deepcopy(MINI_CONFIG))


class _FakeBackend:
    def __init__(self):
        self.calls = []

    def reduce_metrics(self, raw_metrics, metric_formats):
        self.calls.append(("reduce_metrics", sorted(raw_metrics.keys()), dict(metric_formats)))
        return {
            "final_total": {
                "mean": 123.0,
                "median": 120.0,
                "std": 12.0,
                "p10": 100.0,
                "p25": 110.0,
                "p75": 130.0,
                "p90": 140.0,
                "format": "dollar",
            }
        }

    def compute_trajectories(self, trajectory_samples):
        self.calls.append(("compute_trajectories", sorted(trajectory_samples.keys())))
        return {
            "total": {
                "p10": [100.0, 200.0, 300.0],
                "p50": [110.0, 210.0, 310.0],
                "p90": [120.0, 220.0, 320.0],
            }
        }

    def evaluate_safety(self, raw_metrics, safety_config):
        self.calls.append(("evaluate_safety", sorted(raw_metrics.keys()), dict(safety_config)))
        return {"chance": [], "cvar": [], "all_passed": True}

    def build_histograms(self, raw_metrics, n_bins):
        self.calls.append(("build_histograms", sorted(raw_metrics.keys()), n_bins))
        return {
            "final_total": {
                "bins": [100.0, 200.0],
                "counts": [3, 7],
                "bin_width": 100.0,
                "lo": 100.0,
                "hi": 300.0,
            }
        }


class _FailingBackend:
    def reduce_metrics(self, raw_metrics, metric_formats):
        raise RuntimeError("backend unavailable")

    def compute_trajectories(self, trajectory_samples):
        raise RuntimeError("backend unavailable")

    def evaluate_safety(self, raw_metrics, safety_config):
        raise RuntimeError("backend unavailable")


class _SamplingOnlyBackend:
    def __init__(self):
        self.calls = []

    def sample_variable_grid(self, variable_specs, n_steps, n_simulations, seed):
        self.calls.append(("sample_variable_grid", sorted(variable_specs.keys()), n_steps, n_simulations, seed))
        self.last_seed = seed
        return {
            "rate": [
                [0.1, 0.1, 0.1],
                [0.5, 0.5, 0.5],
            ]
        }


class _ExprSamplingBackend:
    def __init__(self):
        self.calls = []

    def sample_binomial(self, trials, probability, seed):
        self.calls.append(("sample_binomial", trials, probability, seed))
        return 7


class TestNativeLoader(unittest.TestCase):
    def test_backend_info_is_shaped(self):
        info = native.backend_info()
        self.assertIn("available", info)
        if not info["available"]:
            self.assertIn("error", info)


class TestKernelNativeIntegration(unittest.TestCase):
    def test_run_monte_carlo_uses_native_backend_when_available(self):
        fake_backend = _FakeBackend()
        with mock.patch.object(kernel, "_get_native_backend", return_value=fake_backend):
            result = kernel.run_monte_carlo(_cfg(), seed=42, n_override=10)

        self.assertEqual(result["stats"]["final_total"]["mean"], 123.0)
        self.assertEqual(result["trajectories"]["total"]["p50"], [110.0, 210.0, 310.0])
        self.assertEqual([call[0] for call in fake_backend.calls], ["reduce_metrics", "compute_trajectories"])

    def test_run_monte_carlo_falls_back_when_native_backend_fails(self):
        with mock.patch.object(kernel, "_get_native_backend", return_value=_FailingBackend()):
            result = kernel.run_monte_carlo(_cfg(), seed=42, n_override=10)

        self.assertIn("final_total", result["stats"])
        self.assertIn("mean", result["stats"]["final_total"])
        self.assertIn("total", result["trajectories"])
        self.assertEqual(len(result["trajectories"]["total"]["p50"]), 3)

    def test_run_monte_carlo_uses_native_batch_sampling_when_available(self):
        sampling_backend = _SamplingOnlyBackend()
        with mock.patch.object(kernel, "_get_native_backend", return_value=sampling_backend):
            result = kernel.run_monte_carlo(_cfg(), seed=42, n_override=2)

        self.assertEqual(sampling_backend.calls[0][0], "sample_variable_grid")
        self.assertEqual(result["stats"]["final_total"]["mean"], 900.0)
        self.assertEqual(result["stats"]["final_total"]["median"], 900.0)
        self.assertEqual(result["trajectories"]["total"]["p50"], [300.0, 600.0, 900.0])

    def test_run_monte_carlo_can_disable_native_batch_sampling(self):
        sampling_backend = _SamplingOnlyBackend()
        with mock.patch.dict(os.environ, {"SIMENGINE_DISABLE_NATIVE_SAMPLING": "1"}):
            with mock.patch.object(kernel, "_get_native_backend", return_value=sampling_backend):
                result = kernel.run_monte_carlo(_cfg(), seed=42, n_override=2)

        self.assertEqual(sampling_backend.calls, [])
        self.assertIn("final_total", result["stats"])

    def test_eval_expr_uses_native_binomial_when_available(self):
        expr_backend = _ExprSamplingBackend()
        with mock.patch.object(kernel, "_get_native_backend", return_value=expr_backend):
            result = kernel.eval_expr("binomial(10, 0.25)", {})

        self.assertEqual(result, 7)
        self.assertEqual(expr_backend.calls[0][0], "sample_binomial")

    def test_eval_expr_can_disable_native_binomial(self):
        expr_backend = _ExprSamplingBackend()
        with mock.patch.dict(os.environ, {"SIMENGINE_DISABLE_NATIVE_EXPR_SAMPLING": "1"}):
            with mock.patch.object(kernel, "_get_native_backend", return_value=expr_backend):
                result = kernel.eval_expr("binomial(3, 1.0)", {})

        self.assertEqual(result, 3)
        self.assertEqual(expr_backend.calls, [])

    def test_evaluate_safety_uses_native_backend_when_available(self):
        fake_backend = _FakeBackend()
        mc_result = {
            "raw_metrics": {"final_total": [100.0, 200.0, 300.0]},
        }
        with mock.patch.object(kernel, "_get_native_backend", return_value=fake_backend):
            result = kernel.evaluate_safety(mc_result, MINI_CONFIG["safety"])

        self.assertTrue(result["all_passed"])
        self.assertEqual(fake_backend.calls[0][0], "evaluate_safety")

    def test_evaluate_safety_falls_back_when_native_backend_fails(self):
        cfg = _cfg()
        mc = kernel.run_monte_carlo(cfg, seed=42, n_override=50)
        with mock.patch.object(kernel, "_get_native_backend", return_value=_FailingBackend()):
            result = kernel.evaluate_safety(mc, MINI_CONFIG["safety"])

        self.assertIn("chance", result)
        self.assertIn("all_passed", result)


class TestServerNativeIntegration(unittest.TestCase):
    def test_build_histograms_uses_native_backend_when_available(self):
        fake_backend = _FakeBackend()
        raw_metrics = {"final_total": [100.0, 120.0, 140.0]}
        with mock.patch.object(server, "_get_native_backend", return_value=fake_backend):
            result = server.build_histograms(raw_metrics, {}, n_bins=2)

        self.assertEqual(result["final_total"]["counts"], [3, 7])
        self.assertEqual(fake_backend.calls[0][0], "build_histograms")

    def test_build_histograms_falls_back_when_native_backend_fails(self):
        raw_metrics = {"final_total": [100.0, 120.0, 140.0]}
        with mock.patch.object(server, "_get_native_backend", return_value=_FailingBackend()):
            result = server.build_histograms(raw_metrics, {}, n_bins=2)

        self.assertEqual(sum(result["final_total"]["counts"]), 3)
        self.assertEqual(len(result["final_total"]["bins"]), 2)


class TestDiagnosticsNativeIntegration(unittest.TestCase):
    def test_convergence_analysis_uses_native_backend_for_checkpoint_stats(self):
        fake_backend = _FakeBackend()
        with mock.patch.object(diagnostics, "_get_native_backend", return_value=fake_backend):
            result = diagnostics.convergence_analysis(
                _cfg(), checkpoints=[10], metric="final_total", seed=42, max_runs=10
            )

        self.assertEqual(result["checkpoints"][0]["mean"], 123.0)
        self.assertEqual(result["checkpoints"][0]["p10"], 100.0)
        self.assertTrue(any(call[0] == "reduce_metrics" for call in fake_backend.calls))

    def test_convergence_analysis_falls_back_when_native_backend_fails(self):
        with mock.patch.object(diagnostics, "_get_native_backend", return_value=_FailingBackend()):
            result = diagnostics.convergence_analysis(
                _cfg(), checkpoints=[10], metric="final_total", seed=42, max_runs=10
            )

        self.assertIn("mean", result["checkpoints"][0])
        self.assertIn("p90", result["checkpoints"][0])


@unittest.skipUnless(native.native_available(), "simengine_native not installed")
class TestNativeParity(unittest.TestCase):
    def test_native_backend_exposes_batch_sampler(self):
        backend = native.get_native_backend()
        self.assertTrue(hasattr(backend, "sample_variable_grid"))

        sampled = backend.sample_variable_grid(
            {"rate": {"distribution": "fixed", "params": {"value": 1.5}}},
            3,
            2,
            42,
        )

        self.assertEqual(sampled["rate"], [[1.5, 1.5, 1.5], [1.5, 1.5, 1.5]])

    def test_native_backend_exposes_binomial_sampler(self):
        backend = native.get_native_backend()
        self.assertTrue(hasattr(backend, "sample_binomial"))
        self.assertEqual(backend.sample_binomial(3, 1.0, 42), 3)

    def test_native_reduce_metrics_matches_python_reducer(self):
        cfg = _cfg()
        with mock.patch.object(kernel, "_get_native_backend", return_value=None):
            mc = kernel.run_monte_carlo(cfg, seed=42, n_override=200)

        metric_formats = kernel._metric_formats(cfg)
        native_stats = native.get_native_backend().reduce_metrics(mc["raw_metrics"], metric_formats)
        python_stats = kernel._compute_stats_python(mc["raw_metrics"], metric_formats)

        self.assertAlmostEqual(native_stats["final_total"]["mean"], python_stats["final_total"]["mean"], places=2)
        self.assertAlmostEqual(native_stats["final_total"]["median"], python_stats["final_total"]["median"], places=2)
        self.assertAlmostEqual(native_stats["final_total"]["p10"], python_stats["final_total"]["p10"], places=2)
        self.assertAlmostEqual(native_stats["final_total"]["p90"], python_stats["final_total"]["p90"], places=2)

    def test_native_evaluate_safety_matches_python(self):
        cfg = _cfg()
        with mock.patch.object(kernel, "_get_native_backend", return_value=None):
            mc = kernel.run_monte_carlo(cfg, seed=42, n_override=200)

        native_result = native.get_native_backend().evaluate_safety(mc["raw_metrics"], MINI_CONFIG["safety"])
        python_result = kernel._evaluate_safety_python(mc["raw_metrics"], MINI_CONFIG["safety"])

        self.assertEqual(native_result["all_passed"], python_result["all_passed"])
        self.assertEqual(len(native_result["chance"]), len(python_result["chance"]))

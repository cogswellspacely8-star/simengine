#!/usr/bin/env python3
"""
SimEngine calibration ledger and proper scoring rules.
=======================================================
Records the engine's probabilistic forecasts, lets you resolve them against
real-world outcomes later, and scores how well-calibrated the forecasts were.

Why this exists: a Monte Carlo engine will always emit a confident-looking
distribution. The only thing that separates "a calculator that produces
plausible numbers" from "a forecasting instrument with a demonstrated hit
rate" is a track record scored against reality. This module is that spine.
Time is the moat — the track record only accumulates if logging starts now.

Pure Python stdlib (sqlite3 / math / datetime / json). Zero dependencies.
"""

import json
import math
import sqlite3
import datetime


# ---------------------------------------------------------------------------
# Proper scoring rules
# ---------------------------------------------------------------------------

def brier_score(predictions, outcomes):
    """Mean squared error between predicted probabilities and binary outcomes.

    0.0 is perfect; 0.25 is the score of always guessing 0.5; 1.0 is worst.
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have equal length")
    if not predictions:
        raise ValueError("need at least one prediction")
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


def log_loss(predictions, outcomes, eps=1e-15):
    """Mean negative log-likelihood of binary outcomes under predicted probs.

    Probabilities are clamped to [eps, 1 - eps] so a confident-and-wrong
    forecast stays finite (heavily penalised) instead of going to infinity.
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have equal length")
    if not predictions:
        raise ValueError("need at least one prediction")
    total = 0.0
    for p, o in zip(predictions, outcomes):
        p = min(max(p, eps), 1.0 - eps)
        total += o * math.log(p) + (1 - o) * math.log(1.0 - p)
    return -total / len(predictions)


def crps_sample(samples, observation):
    """Continuous Ranked Probability Score for an ensemble/sample forecast.

    Energy-form estimator:
        CRPS = (1/n) * sum_i |x_i - y|  -  (1/(2 n^2)) * sum_i sum_j |x_i - x_j|

    For a single-point (deterministic) forecast this reduces to the absolute
    error |x - y|. Lower is better; 0.0 is a perfect point forecast.
    """
    if not samples:
        raise ValueError("need at least one sample")
    n = len(samples)
    term1 = sum(abs(x - observation) for x in samples) / n
    term2 = sum(abs(xi - xj) for xi in samples for xj in samples) / (2 * n * n)
    return term1 - term2


# ---------------------------------------------------------------------------
# Forecast ledger
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS forecasts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    question       TEXT NOT NULL,
    predicted_prob REAL NOT NULL,
    config_hash    TEXT,
    metric         TEXT,
    samples_json   TEXT,
    created_at     TEXT NOT NULL,
    resolve_by     TEXT,
    resolved_at    TEXT,
    outcome        INTEGER
);
"""


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class CalibrationLedger:
    """A durable, timestamped log of forecasts and their realized outcomes.

    Record a probabilistic forecast now; resolve it against the real binary
    outcome later; ask for the Brier / log-loss score over everything resolved
    so far. Backed by sqlite3 so the track record survives restarts.
    """

    def __init__(self, db_path=":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def record(self, question, predicted_prob, *, config_hash=None,
               metric=None, samples=None, created_at=None, resolve_by=None):
        """Log a forecast. Returns its integer id (use it to resolve later).

        resolve_by: optional ISO date string for when the outcome is known.
        """
        if not 0.0 <= predicted_prob <= 1.0:
            raise ValueError("predicted_prob must be in [0, 1]")
        samples_json = json.dumps(list(samples)) if samples is not None else None
        cur = self.conn.execute(
            "INSERT INTO forecasts "
            "(question, predicted_prob, config_hash, metric, samples_json, created_at, resolve_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (question, predicted_prob, config_hash, metric, samples_json,
             created_at or _utcnow(), resolve_by),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def all_forecasts(self):
        """Every forecast (pending and resolved), oldest first."""
        rows = self.conn.execute("SELECT * FROM forecasts ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def resolve(self, forecast_id, outcome, *, resolved_at=None):
        """Record the realized binary outcome (0 or 1) for a logged forecast."""
        o = int(outcome)
        if o not in (0, 1):
            raise ValueError("outcome must be 0 or 1")
        cur = self.conn.execute(
            "UPDATE forecasts SET outcome = ?, resolved_at = ? WHERE id = ?",
            (o, resolved_at or _utcnow(), forecast_id),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"no forecast with id {forecast_id}")

    def resolved(self):
        """Return all resolved forecasts (outcome recorded), oldest first."""
        rows = self.conn.execute(
            "SELECT * FROM forecasts WHERE outcome IS NOT NULL ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def score(self):
        """Brier and log-loss over every resolved forecast.

        Returns {"n": 0, "brier": None, "log_loss": None} when nothing has
        been resolved yet.
        """
        rows = self.resolved()
        if not rows:
            return {"n": 0, "brier": None, "log_loss": None}
        preds = [r["predicted_prob"] for r in rows]
        outs = [r["outcome"] for r in rows]
        return {
            "n": len(rows),
            "brier": brier_score(preds, outs),
            "log_loss": log_loss(preds, outs),
        }

    def reliability_curve(self, n_bins=10):
        """Per-bucket calibration points over resolved forecasts.

        Predicted probabilities are binned into n_bins equal-width buckets
        [0, 1/n), ... [1 - 1/n, 1] (the last bucket includes 1.0). Each
        non-empty bucket reports its count, mean predicted probability, and
        observed outcome frequency. Empty buckets are omitted; [] when nothing
        is resolved. Built from the raw resolved set, not interpolated stats.
        """
        rows = self.resolved()
        if not rows:
            return []
        width = 1.0 / n_bins
        buckets = [[] for _ in range(n_bins)]
        for r in rows:
            p = r["predicted_prob"]
            idx = min(int(p / width), n_bins - 1)
            buckets[idx].append((p, r["outcome"]))
        curve = []
        for i, b in enumerate(buckets):
            if not b:
                continue
            ps = [p for p, _ in b]
            outs_b = [o for _, o in b]
            curve.append({
                "lo": round(i * width, 4),
                "hi": round((i + 1) * width, 4),
                "count": len(b),
                "mean_predicted": round(sum(ps) / len(ps), 4),
                "observed_freq": round(sum(outs_b) / len(outs_b), 4),
            })
        return curve

    def expected_calibration_error(self, n_bins=10):
        """Count-weighted mean gap between predicted and observed per bucket.

        ECE = sum_bins (count / N) * |observed_freq - mean_predicted|. None when
        no forecasts are resolved.
        """
        curve = self.reliability_curve(n_bins)
        if not curve:
            return None
        total = sum(b["count"] for b in curve)
        return round(
            sum(b["count"] / total * abs(b["observed_freq"] - b["mean_predicted"])
                for b in curve),
            4,
        )

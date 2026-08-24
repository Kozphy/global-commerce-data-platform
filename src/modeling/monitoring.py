"""Lightweight post-deployment model monitoring primitives."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class MonitoringSnapshot:
    mean_prediction: float
    mean_latency_ms: float
    feature_missing_rate: float


def summarize_serving(predictions: list[float], latencies_ms: list[float], missing_flags: list[bool]) -> MonitoringSnapshot:
    if not predictions or not latencies_ms or not missing_flags:
        raise ValueError("monitoring inputs must be non-empty")
    if not (len(predictions) == len(latencies_ms) == len(missing_flags)):
        raise ValueError("monitoring inputs must have equal lengths")
    return MonitoringSnapshot(
        mean_prediction=mean(predictions),
        mean_latency_ms=mean(latencies_ms),
        feature_missing_rate=sum(missing_flags) / len(missing_flags),
    )


def detect_drift(reference: MonitoringSnapshot, current: MonitoringSnapshot, *, prediction_delta: float = 0.15, latency_ratio: float = 1.5, missing_rate_delta: float = 0.05) -> dict[str, bool]:
    """Return interpretable alert flags; thresholds are explicit and configurable."""
    prediction_scale = max(abs(reference.mean_prediction), 1e-9)
    return {
        "prediction_drift": abs(current.mean_prediction - reference.mean_prediction) / prediction_scale > prediction_delta,
        "latency_regression": current.mean_latency_ms > reference.mean_latency_ms * latency_ratio,
        "feature_quality_drift": current.feature_missing_rate - reference.feature_missing_rate > missing_rate_delta,
    }

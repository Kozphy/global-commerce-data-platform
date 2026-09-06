"""CI-friendly quality gate for offline recommendation metrics and serving latency."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    reasons: list[str]


def evaluate_quality_gate(
    *,
    ndcg_at_k: float,
    recall_at_k: float,
    latency_ms: float,
    min_ndcg_at_k: float = 0.10,
    min_recall_at_k: float = 0.10,
    max_latency_ms: float = 100.0,
) -> QualityGateResult:
    reasons: list[str] = []
    if ndcg_at_k < min_ndcg_at_k:
        reasons.append(f"ndcg_at_k {ndcg_at_k:.4f} < {min_ndcg_at_k:.4f}")
    if recall_at_k < min_recall_at_k:
        reasons.append(f"recall_at_k {recall_at_k:.4f} < {min_recall_at_k:.4f}")
    if latency_ms > max_latency_ms:
        reasons.append(f"latency_ms {latency_ms:.2f} > {max_latency_ms:.2f}")
    return QualityGateResult(passed=not reasons, reasons=reasons)

"""Offline ranking evaluation for recommendation experiments."""

from __future__ import annotations

from math import log2


def precision_at_k(predicted: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    top_k = predicted[:k]
    if not top_k:
        return 0.0
    return sum(item in relevant for item in top_k) / k


def recall_at_k(predicted: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return sum(item in relevant for item in predicted[:k]) / len(relevant)


def ndcg_at_k(predicted: list[str], relevant: set[str], k: int) -> float:
    dcg = sum((1.0 / log2(rank + 2)) for rank, item in enumerate(predicted[:k]) if item in relevant)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / log2(rank + 2) for rank in range(ideal_hits))
    return dcg / idcg if idcg else 0.0


def reciprocal_rank_at_k(predicted: list[str], relevant: set[str], k: int) -> float:
    for rank, item in enumerate(predicted[:k], start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ranking_metrics(predicted: list[str], relevant: set[str], k: int = 10) -> dict[str, float]:
    return {
        f"precision@{k}": precision_at_k(predicted, relevant, k),
        f"recall@{k}": recall_at_k(predicted, relevant, k),
        f"ndcg@{k}": ndcg_at_k(predicted, relevant, k),
        f"mrr@{k}": reciprocal_rank_at_k(predicted, relevant, k),
    }

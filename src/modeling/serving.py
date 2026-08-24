"""Recommendation-serving boundary with latency measurement and model version metadata."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from .matrix_factorization import MatrixFactorizationRecommender
from .registry import ModelMetadata


@dataclass(frozen=True)
class RecommendationResponse:
    user_id: str
    items: list[str]
    model_name: str
    model_version: str
    latency_ms: float


class RecommendationService:
    def __init__(self, model: MatrixFactorizationRecommender, metadata: ModelMetadata) -> None:
        self.model = model
        self.metadata = metadata

    def recommend(self, user_id: str, *, k: int = 10) -> RecommendationResponse:
        if k < 1:
            raise ValueError("k must be at least 1")
        started = perf_counter()
        items = self.model.recommend(user_id, k=k)
        latency_ms = (perf_counter() - started) * 1000.0
        return RecommendationResponse(
            user_id=str(user_id),
            items=items,
            model_name=self.metadata.model_name,
            model_version=self.metadata.version,
            latency_ms=latency_ms,
        )

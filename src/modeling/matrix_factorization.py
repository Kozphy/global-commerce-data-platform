"""Small explicit-feedback matrix factorization model for portfolio experiments."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass
class MFConfig:
    factors: int = 8
    learning_rate: float = 0.03
    regularization: float = 0.02
    epochs: int = 20
    seed: int = 42


class MatrixFactorizationRecommender:
    """SGD matrix factorization with deterministic initialization."""

    def __init__(self, config: MFConfig | None = None) -> None:
        self.config = config or MFConfig()
        self.user_factors: dict[str, list[float]] = {}
        self.item_factors: dict[str, list[float]] = {}
        self.global_mean = 0.0
        self.seen: dict[str, set[str]] = {}

    def _vector(self, rng: random.Random) -> list[float]:
        scale = 1.0 / math.sqrt(self.config.factors)
        return [rng.uniform(-scale, scale) for _ in range(self.config.factors)]

    def fit(
        self,
        rows: Iterable[Mapping],
        *,
        user_key: str = "user_id",
        item_key: str = "item_id",
        rating_key: str = "rating",
    ) -> MatrixFactorizationRecommender:
        data = [(str(r[user_key]), str(r[item_key]), float(r[rating_key])) for r in rows]
        if not data:
            raise ValueError("training data cannot be empty")

        self.global_mean = sum(r for _, _, r in data) / len(data)
        rng = random.Random(self.config.seed)
        for user, item, _ in data:
            self.user_factors.setdefault(user, self._vector(rng))
            self.item_factors.setdefault(item, self._vector(rng))
            self.seen.setdefault(user, set()).add(item)

        for _ in range(self.config.epochs):
            rng.shuffle(data)
            for user, item, rating in data:
                pu = self.user_factors[user]
                qi = self.item_factors[item]
                pred = self.global_mean + sum(a * b for a, b in zip(pu, qi, strict=True))
                err = rating - pred
                for idx in range(self.config.factors):
                    old_p = pu[idx]
                    old_q = qi[idx]
                    pu[idx] += self.config.learning_rate * (
                        err * old_q - self.config.regularization * old_p
                    )
                    qi[idx] += self.config.learning_rate * (
                        err * old_p - self.config.regularization * old_q
                    )
        return self

    def predict(self, user_id: str, item_id: str) -> float:
        pu = self.user_factors.get(str(user_id))
        qi = self.item_factors.get(str(item_id))
        if pu is None or qi is None:
            return self.global_mean
        return self.global_mean + sum(a * b for a, b in zip(pu, qi, strict=True))

    def recommend(self, user_id: str, *, k: int = 10) -> list[str]:
        user = str(user_id)
        consumed = self.seen.get(user, set())
        candidates = [item for item in self.item_factors if item not in consumed]
        ranked = sorted(candidates, key=lambda item: (-self.predict(user, item), item))
        return ranked[:k]

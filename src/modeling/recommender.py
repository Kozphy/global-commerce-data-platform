"""Small, explainable recommendation baselines for portfolio experiments.

The implementations intentionally avoid opaque infrastructure so interviewers can
inspect the ranking logic, reproduce experiments, and compare baselines.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import sqrt
from typing import Iterable

Interaction = tuple[str, str]


@dataclass
class PopularityRecommender:
    """Global popularity baseline used as a minimum bar for ML recommenders."""

    item_counts: Counter[str] | None = None

    def fit(self, interactions: Iterable[Interaction]) -> "PopularityRecommender":
        self.item_counts = Counter(item for _, item in interactions)
        return self

    def recommend(self, user_id: str, k: int = 10, seen: set[str] | None = None) -> list[str]:
        del user_id  # popularity is intentionally user-agnostic
        if self.item_counts is None:
            raise RuntimeError("fit must be called before recommend")
        seen = seen or set()
        return [item for item, _ in self.item_counts.most_common() if item not in seen][:k]


@dataclass
class UserItemRecommender:
    """User-based collaborative-filtering baseline with cosine similarity."""

    user_items: dict[str, set[str]] | None = None

    def fit(self, interactions: Iterable[Interaction]) -> "UserItemRecommender":
        mapping: dict[str, set[str]] = defaultdict(set)
        for user_id, item_id in interactions:
            mapping[user_id].add(item_id)
        self.user_items = dict(mapping)
        return self

    @staticmethod
    def _cosine(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / sqrt(len(a) * len(b))

    def recommend(self, user_id: str, k: int = 10) -> list[str]:
        if self.user_items is None:
            raise RuntimeError("fit must be called before recommend")
        target = self.user_items.get(user_id, set())
        scores: Counter[str] = Counter()
        for other_user, items in self.user_items.items():
            if other_user == user_id:
                continue
            similarity = self._cosine(target, items)
            if similarity <= 0:
                continue
            for item in items - target:
                scores[item] += similarity
        return [item for item, _ in scores.most_common(k)]

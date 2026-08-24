"""Leakage-resistant temporal train/validation/test utilities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TemporalSplit:
    train: list[dict]
    validation: list[dict]
    test: list[dict]


def temporal_split(
    rows: Iterable[Mapping],
    *,
    timestamp_key: str = "timestamp",
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> TemporalSplit:
    """Split interactions chronologically so future events never leak into training."""
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("validation_fraction and test_fraction must be in (0, 1)")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("validation_fraction + test_fraction must be < 1")

    materialized = [dict(row) for row in rows]
    if len(materialized) < 3:
        raise ValueError("at least three rows are required for a temporal split")

    def parsed(row: Mapping) -> datetime:
        value = row[timestamp_key]
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    materialized.sort(key=parsed)
    n = len(materialized)
    n_test = max(1, int(round(n * test_fraction)))
    n_validation = max(1, int(round(n * validation_fraction)))
    n_train = n - n_validation - n_test
    if n_train < 1:
        raise ValueError("fractions leave no rows for training")

    return TemporalSplit(
        train=materialized[:n_train],
        validation=materialized[n_train : n_train + n_validation],
        test=materialized[n_train + n_validation :],
    )

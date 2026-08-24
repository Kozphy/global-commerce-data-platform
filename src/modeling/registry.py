"""Minimal JSON model registry for reproducible portfolio deployments."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .matrix_factorization import MFConfig, MatrixFactorizationRecommender


@dataclass(frozen=True)
class ModelMetadata:
    model_name: str
    version: str
    created_at: str
    metrics: dict[str, float]


def save_matrix_factorization(
    model: MatrixFactorizationRecommender,
    path: str | Path,
    *,
    version: str,
    metrics: dict[str, float] | None = None,
) -> ModelMetadata:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata = ModelMetadata(
        model_name="matrix_factorization",
        version=version,
        created_at=datetime.now(UTC).isoformat(),
        metrics=metrics or {},
    )
    payload = {
        "metadata": asdict(metadata),
        "config": asdict(model.config),
        "global_mean": model.global_mean,
        "user_factors": model.user_factors,
        "item_factors": model.item_factors,
        "seen": {user: sorted(items) for user, items in model.seen.items()},
    }
    destination.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return metadata


def load_matrix_factorization(path: str | Path) -> tuple[MatrixFactorizationRecommender, ModelMetadata]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    model = MatrixFactorizationRecommender(MFConfig(**payload["config"]))
    model.global_mean = float(payload["global_mean"])
    model.user_factors = {
        str(user): [float(value) for value in vector]
        for user, vector in payload["user_factors"].items()
    }
    model.item_factors = {
        str(item): [float(value) for value in vector]
        for item, vector in payload["item_factors"].items()
    }
    model.seen = {str(user): set(items) for user, items in payload["seen"].items()}
    metadata = ModelMetadata(**payload["metadata"])
    return model, metadata

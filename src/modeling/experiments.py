"""Reproducible experiment tracking and lightweight hyperparameter search."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .matrix_factorization import MatrixFactorizationRecommender, MFConfig


@dataclass(frozen=True)
class ExperimentResult:
    run_id: str
    model: str
    params: dict
    metrics: dict[str, float]
    created_at: str


def run_grid_search(
    train_rows: Iterable[dict],
    validation_rows: Iterable[dict],
    evaluator: Callable[[MatrixFactorizationRecommender, list[dict]], dict[str, float]],
    *,
    factors: tuple[int, ...] = (4, 8, 16),
    learning_rates: tuple[float, ...] = (0.01, 0.03),
    regularizations: tuple[float, ...] = (0.01, 0.05),
    epochs: tuple[int, ...] = (10, 20),
    objective: str = "ndcg_at_k",
) -> tuple[MatrixFactorizationRecommender, ExperimentResult, list[ExperimentResult]]:
    """Deterministic search that is CI-safe and easy to explain in interviews."""
    train = list(train_rows)
    validation = list(validation_rows)
    all_results: list[ExperimentResult] = []
    best_model: MatrixFactorizationRecommender | None = None
    best_result: ExperimentResult | None = None

    counter = 0
    for factor_count in factors:
        for lr in learning_rates:
            for reg in regularizations:
                for epoch_count in epochs:
                    counter += 1
                    cfg = MFConfig(
                        factors=factor_count,
                        learning_rate=lr,
                        regularization=reg,
                        epochs=epoch_count,
                    )
                    model = MatrixFactorizationRecommender(cfg).fit(train)
                    metrics = evaluator(model, validation)
                    result = ExperimentResult(
                        run_id=f"mf-{counter:04d}",
                        model="matrix_factorization",
                        params=asdict(cfg),
                        metrics=metrics,
                        created_at=datetime.now(UTC).isoformat(),
                    )
                    all_results.append(result)
                    if best_result is None or metrics[objective] > best_result.metrics[objective]:
                        best_model = model
                        best_result = result

    if best_model is None or best_result is None:
        raise ValueError("hyperparameter search produced no trials")
    return best_model, best_result, all_results


def append_experiment(result: ExperimentResult, path: str | Path) -> None:
    """Append one JSONL experiment record for auditability and comparison."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")

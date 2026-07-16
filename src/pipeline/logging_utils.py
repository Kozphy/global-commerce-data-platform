from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit machine-readable JSON log lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "run_id",
            "pipeline_stage",
            "dataset",
            "row_count",
            "duration_ms",
            "status",
            "error_type",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure root logging once for pipeline and API processes."""
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level.upper())
        return

    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    run_id: str | None = None,
    pipeline_stage: str | None = None,
    dataset: str | None = None,
    row_count: int | None = None,
    duration_ms: float | None = None,
    status: str | None = None,
    error_type: str | None = None,
    **extra: Any,
) -> None:
    """Log a structured pipeline event without dumping sensitive record payloads."""
    # Drop any accidental sensitive extras.
    for banned in ("email", "full_name", "record", "records", "row", "rows"):
        extra.pop(banned, None)
    logger.log(
        level,
        message,
        extra={
            "run_id": run_id,
            "pipeline_stage": pipeline_stage,
            "dataset": dataset,
            "row_count": row_count,
            "duration_ms": duration_ms,
            "status": status,
            "error_type": error_type,
            **extra,
        },
    )

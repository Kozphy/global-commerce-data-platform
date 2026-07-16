"""Pipeline run metadata and high-water mark persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid4().hex[:8]}"


@dataclass
class QualityCheckResult:
    name: str
    passed: bool
    detail: str
    severity: str = "warning"  # warning | critical


@dataclass
class PipelineRunRecord:
    run_id: str
    status: str = "running"
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    input_row_counts: dict[str, int] = field(default_factory=dict)
    accepted_row_counts: dict[str, int] = field(default_factory=dict)
    rejected_row_counts: dict[str, int] = field(default_factory=dict)
    output_row_counts: dict[str, int] = field(default_factory=dict)
    quality_checks: list[dict[str, Any]] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    high_water_marks_before: dict[str, str | None] = field(default_factory=dict)
    high_water_marks_after: dict[str, str | None] = field(default_factory=dict)
    is_full_load: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HighWaterMarks:
    """Persistent incremental cursors.

    Incremental key for orders: ``order_ts`` (ISO-8601 UTC).
    Incremental key for customers: ``created_at`` (ISO-8601 UTC).

    Limitations:
    - Late-arriving records with timestamps at or below the watermark are skipped.
    - Clock skew / out-of-order source events can cause missed rows.
    - First successful run is always a full load (watermarks start empty).
    """

    customers: str | None = None
    orders: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"customers": self.customers, "orders": self.orders}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HighWaterMarks:
        data = data or {}
        return cls(
            customers=data.get("customers"),
            orders=data.get("orders"),
        )


class StateStore:
    """JSON-backed local state for watermarks and run history."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.watermark_path = self.state_dir / "high_water_marks.json"
        self.runs_path = self.state_dir / "pipeline_runs.jsonl"
        self.latest_path = self.state_dir / "latest_run.json"

    def load_watermarks(self) -> HighWaterMarks:
        if not self.watermark_path.exists():
            return HighWaterMarks()
        data = json.loads(self.watermark_path.read_text(encoding="utf-8"))
        return HighWaterMarks.from_dict(data)

    def save_watermarks(self, marks: HighWaterMarks) -> None:
        self.watermark_path.write_text(
            json.dumps(marks.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    def append_run(self, record: PipelineRunRecord) -> None:
        with self.runs_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict()) + "\n")
        self.latest_path.write_text(
            json.dumps(record.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    def load_latest_run(self) -> dict[str, Any] | None:
        if not self.latest_path.exists():
            return None
        return json.loads(self.latest_path.read_text(encoding="utf-8"))

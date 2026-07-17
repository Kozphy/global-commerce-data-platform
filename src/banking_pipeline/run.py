from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import duckdb
from pydantic import ValidationError

from banking_ai.models import DigitalEvent

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = Path(os.getenv("DBAI_EVENTS_PATH", ROOT / "data" / "banking_raw" / "events.jsonl"))
GOLD_PATH = Path(
    os.getenv("DBAI_DUCKDB_PATH", ROOT / "data" / "banking_gold" / "banking.duckdb")
)
REJECT_PATH = Path(
    os.getenv("DBAI_REJECT_PATH", ROOT / "data" / "banking_quality" / "rejects.jsonl")
)


def load_events(path: Path) -> tuple[list[DigitalEvent], list[dict[str, Any]]]:
    accepted: list[DigitalEvent] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            event = DigitalEvent.model_validate(raw)
            if event.event_id in seen:
                raise ValueError("duplicate event_id")
            seen.add(event.event_id)
            accepted.append(event)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            rejected.append({"line": line_number, "error": str(exc), "raw": line})
    return accepted, rejected


def build_warehouse(events: list[DigitalEvent], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_digital_event (
                event_id VARCHAR PRIMARY KEY,
                customer_id VARCHAR NOT NULL,
                event_ts TIMESTAMP NOT NULL,
                event_type VARCHAR NOT NULL,
                channel VARCHAR NOT NULL,
                session_id VARCHAR NOT NULL,
                metadata JSON NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT OR REPLACE INTO fact_digital_event
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event.event_id,
                    event.customer_id,
                    event.event_ts,
                    event.event_type,
                    event.channel,
                    event.session_id,
                    json.dumps(event.metadata),
                )
                for event in events
            ],
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE customer_features AS
            WITH anchor AS (
                SELECT MAX(event_ts) AS as_of FROM fact_digital_event
            )
            SELECT
                customer_id,
                COUNT(*) FILTER (
                    WHERE event_type = 'login_success' AND event_ts >= as_of - INTERVAL 30 DAY
                ) AS login_30d,
                COUNT(*) FILTER (
                    WHERE event_type = 'login_failed' AND event_ts >= as_of - INTERVAL 7 DAY
                ) AS failed_login_7d,
                COUNT(*) FILTER (
                    WHERE event_type = 'transfer_completed' AND event_ts >= as_of - INTERVAL 30 DAY
                ) AS transfers_30d,
                COALESCE(SUM(CAST(json_extract_string(metadata, '$.amount') AS DOUBLE)) FILTER (
                    WHERE event_type = 'transfer_completed' AND event_ts >= as_of - INTERVAL 1 DAY
                ), 0) AS transfer_amount_24h,
                COUNT(*) FILTER (
                    WHERE event_type = 'product_view' AND event_ts >= as_of - INTERVAL 30 DAY
                ) AS product_views_30d,
                COUNT(*) FILTER (
                    WHERE event_type = 'device_changed' AND event_ts >= as_of - INTERVAL 7 DAY
                ) AS device_change_7d,
                COUNT(*) FILTER (
                    WHERE event_type = 'journey_abandoned' AND event_ts >= as_of - INTERVAL 30 DAY
                ) AS abandonment_30d,
                MAX(event_ts) AS last_event_ts
            FROM fact_digital_event, anchor
            GROUP BY customer_id
            """
        )
    finally:
        connection.close()


def run() -> dict[str, int | str]:
    events, rejects = load_events(RAW_PATH)
    REJECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REJECT_PATH.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in rejects), encoding="utf-8"
    )
    build_warehouse(events, GOLD_PATH)
    return {"accepted": len(events), "rejected": len(rejects), "warehouse": str(GOLD_PATH)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

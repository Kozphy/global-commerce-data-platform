"""Incremental loading, watermark, and idempotency tests."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from pipeline.config import Settings
from pipeline.run import run_pipeline
from pipeline.state import StateStore


def _order_count(db_path: Path) -> int:
    with duckdb.connect(str(db_path)) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM fact_order").fetchone()[0])


def test_full_load_then_idempotent_rerun(tmp_project: Settings):
    first = run_pipeline(tmp_project)
    assert first.status == "success"
    assert first.is_full_load is True
    count1 = _order_count(tmp_project.duckdb_path)

    second = run_pipeline(tmp_project)
    assert second.status == "success"
    assert second.is_full_load is False
    count2 = _order_count(tmp_project.duckdb_path)
    assert count1 == count2 == 2
    assert second.accepted_row_counts["orders"] == 0


def test_incremental_processes_only_new_orders(tmp_project: Settings):
    run_pipeline(tmp_project)
    assert _order_count(tmp_project.duckdb_path) == 2

    orders_path = tmp_project.raw_dir / "orders.json"
    orders = json.loads(orders_path.read_text(encoding="utf-8"))
    orders.append(
        {
            "order_id": "O1999",
            "customer_id": "C001",
            "order_ts": "2024-08-01T12:00:00Z",
            "quantity": 1,
            "unit_price": 10.0,
            "currency": "USD",
            "product_sku": "SKU-Z",
        }
    )
    orders_path.write_text(json.dumps(orders), encoding="utf-8")

    third = run_pipeline(tmp_project)
    assert third.status == "success"
    assert third.accepted_row_counts["orders"] == 1
    assert _order_count(tmp_project.duckdb_path) == 3


def test_failed_run_does_not_advance_watermark(tmp_project: Settings):
    run_pipeline(tmp_project)
    state = StateStore(tmp_project.state_dir)
    marks_before = state.load_watermarks()

    # Corrupt orders JSON to force failure
    (tmp_project.raw_dir / "orders.json").write_text("{not-json", encoding="utf-8")
    try:
        run_pipeline(tmp_project)
        raised = False
    except Exception:
        raised = True
    assert raised

    marks_after = state.load_watermarks()
    assert marks_after.to_dict() == marks_before.to_dict()
    latest = state.load_latest_run()
    assert latest is not None
    assert latest["status"] == "failed"


def test_mart_reconciles_to_facts(tmp_project: Settings):
    run_pipeline(tmp_project)
    with duckdb.connect(str(tmp_project.duckdb_path)) as conn:
        fact_sum = conn.execute("SELECT SUM(gross_sales) FROM fact_order").fetchone()[0]
        mart_sum = conn.execute("SELECT SUM(gross_sales) FROM mart_daily_sales").fetchone()[0]
        assert float(fact_sum) == float(mart_sum)
        orphans = conn.execute(
            """
            SELECT COUNT(*) FROM fact_order f
            LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
            WHERE c.customer_id IS NULL
            """
        ).fetchone()[0]
        assert orphans == 0

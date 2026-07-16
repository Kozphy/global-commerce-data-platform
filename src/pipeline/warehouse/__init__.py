"""DuckDB gold warehouse: star schema, marts, and metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from pipeline.exceptions import WarehouseError
from pipeline.logging_utils import log_event

logger = logging.getLogger(__name__)

# Table grains (documented for interview / Power BI):
# - dim_customer: one row per customer_id (current attributes)
# - fact_order: one row per order_id
# - mart_daily_sales: one row per order_date
# - mart_customer_value: one row per customer_id
# - v_powerbi_sales: one row per (order_date, customer_id)


DDL = """
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id VARCHAR PRIMARY KEY,
    email VARCHAR NOT NULL,
    country VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    full_name VARCHAR NOT NULL,
    loaded_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS fact_order (
    order_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR NOT NULL,
    order_ts TIMESTAMP NOT NULL,
    order_date DATE NOT NULL,
    quantity DOUBLE NOT NULL CHECK (quantity > 0),
    unit_price DOUBLE NOT NULL CHECK (unit_price >= 0),
    currency VARCHAR NOT NULL,
    product_sku VARCHAR NOT NULL,
    gross_sales DOUBLE NOT NULL CHECK (gross_sales >= 0),
    recognized_revenue DOUBLE NOT NULL CHECK (recognized_revenue >= 0),
    loaded_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS mart_daily_sales (
    order_date DATE PRIMARY KEY,
    order_count BIGINT NOT NULL,
    units_sold DOUBLE NOT NULL,
    gross_sales DOUBLE NOT NULL,
    recognized_revenue DOUBLE NOT NULL,
    avg_order_value DOUBLE NOT NULL
);

CREATE TABLE IF NOT EXISTS mart_customer_value (
    customer_id VARCHAR PRIMARY KEY,
    country VARCHAR,
    order_count BIGINT NOT NULL,
    units_sold DOUBLE NOT NULL,
    gross_sales DOUBLE NOT NULL,
    recognized_revenue DOUBLE NOT NULL,
    avg_order_value DOUBLE NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_run_metadata (
    run_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    input_row_counts VARCHAR,
    accepted_row_counts VARCHAR,
    rejected_row_counts VARCHAR,
    output_row_counts VARCHAR,
    quality_checks VARCHAR,
    error_type VARCHAR,
    error_message VARCHAR,
    high_water_marks_before VARCHAR,
    high_water_marks_after VARCHAR,
    is_full_load BOOLEAN
);

CREATE OR REPLACE VIEW v_powerbi_sales AS
SELECT
    f.order_date,
    f.customer_id,
    c.country AS customer_country,
    COUNT(*) AS order_count,
    SUM(f.quantity) AS units_sold,
    SUM(f.gross_sales) AS gross_sales,
    SUM(f.recognized_revenue) AS recognized_revenue,
    CASE WHEN COUNT(*) = 0 THEN 0 ELSE SUM(f.gross_sales) / COUNT(*) END AS average_order_value
FROM fact_order f
JOIN dim_customer c ON f.customer_id = c.customer_id
GROUP BY f.order_date, f.customer_id, c.country;
"""


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def initialize_warehouse(conn: duckdb.DuckDBPyConnection) -> None:
    try:
        conn.execute(DDL)
    except Exception as exc:  # noqa: BLE001
        raise WarehouseError("Failed to initialize warehouse schema") from exc


def upsert_customers(conn: duckdb.DuckDBPyConnection, customers: pd.DataFrame) -> int:
    if customers.empty:
        return 0
    try:
        conn.register("_stg_customers", customers)
        conn.execute(
            """
            INSERT OR REPLACE INTO dim_customer (
                customer_id, email, country, created_at, full_name, loaded_at
            )
            SELECT
                customer_id,
                email,
                country,
                CAST(created_at AS TIMESTAMP),
                full_name,
                current_timestamp
            FROM _stg_customers
            """
        )
        conn.unregister("_stg_customers")
        return len(customers)
    except Exception as exc:  # noqa: BLE001
        raise WarehouseError("Failed to upsert dim_customer") from exc


def upsert_orders(conn: duckdb.DuckDBPyConnection, orders: pd.DataFrame) -> int:
    if orders.empty:
        return 0
    try:
        conn.register("_stg_orders", orders)
        conn.execute(
            """
            INSERT OR REPLACE INTO fact_order (
                order_id, customer_id, order_ts, order_date, quantity, unit_price,
                currency, product_sku, gross_sales, recognized_revenue, loaded_at
            )
            SELECT
                order_id,
                customer_id,
                CAST(order_ts AS TIMESTAMP),
                CAST(order_date AS DATE),
                quantity,
                unit_price,
                currency,
                product_sku,
                gross_sales,
                recognized_revenue,
                current_timestamp
            FROM _stg_orders
            """
        )
        conn.unregister("_stg_orders")
        return len(orders)
    except Exception as exc:  # noqa: BLE001
        raise WarehouseError("Failed to upsert fact_order") from exc


def refresh_marts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Rebuild mart tables deterministically from facts/dimensions."""
    try:
        conn.execute("DELETE FROM mart_daily_sales")
        conn.execute(
            """
            INSERT INTO mart_daily_sales (
                order_date, order_count, units_sold, gross_sales,
                recognized_revenue, avg_order_value
            )
            SELECT
                order_date,
                COUNT(*) AS order_count,
                SUM(quantity) AS units_sold,
                SUM(gross_sales) AS gross_sales,
                SUM(recognized_revenue) AS recognized_revenue,
                CASE WHEN COUNT(*) = 0 THEN 0 ELSE SUM(gross_sales) / COUNT(*) END
                    AS avg_order_value
            FROM fact_order
            GROUP BY order_date
            ORDER BY order_date
            """
        )
        conn.execute("DELETE FROM mart_customer_value")
        conn.execute(
            """
            INSERT INTO mart_customer_value (
                customer_id, country, order_count, units_sold, gross_sales,
                recognized_revenue, avg_order_value
            )
            SELECT
                f.customer_id,
                c.country,
                COUNT(*) AS order_count,
                SUM(f.quantity) AS units_sold,
                SUM(f.gross_sales) AS gross_sales,
                SUM(f.recognized_revenue) AS recognized_revenue,
                CASE WHEN COUNT(*) = 0 THEN 0 ELSE SUM(f.gross_sales) / COUNT(*) END
                    AS avg_order_value
            FROM fact_order f
            LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
            GROUP BY f.customer_id, c.country
            ORDER BY f.customer_id
            """
        )
        daily = conn.execute("SELECT COUNT(*) FROM mart_daily_sales").fetchone()[0]
        cust = conn.execute("SELECT COUNT(*) FROM mart_customer_value").fetchone()[0]
        return {"mart_daily_sales": int(daily), "mart_customer_value": int(cust)}
    except Exception as exc:  # noqa: BLE001
        raise WarehouseError("Failed to refresh marts") from exc


def record_run_metadata(conn: duckdb.DuckDBPyConnection, record: dict[str, Any]) -> None:
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_run_metadata (
                run_id, status, started_at, completed_at,
                input_row_counts, accepted_row_counts, rejected_row_counts,
                output_row_counts, quality_checks, error_type, error_message,
                high_water_marks_before, high_water_marks_after, is_full_load
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record["run_id"],
                record["status"],
                record["started_at"],
                record.get("completed_at"),
                json.dumps(record.get("input_row_counts") or {}),
                json.dumps(record.get("accepted_row_counts") or {}),
                json.dumps(record.get("rejected_row_counts") or {}),
                json.dumps(record.get("output_row_counts") or {}),
                json.dumps(record.get("quality_checks") or []),
                record.get("error_type"),
                record.get("error_message"),
                json.dumps(record.get("high_water_marks_before") or {}),
                json.dumps(record.get("high_water_marks_after") or {}),
                bool(record.get("is_full_load")),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        raise WarehouseError("Failed to write pipeline_run_metadata") from exc


def verify_warehouse_quality(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Post-load verification checks for uniqueness, FK, and non-negative measures."""
    checks: list[dict[str, Any]] = []

    def _scalar(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    dup_customers = _scalar(
        "SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM dim_customer"
    )
    dup_orders = _scalar("SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM fact_order")
    orphan_fk = _scalar(
        """
        SELECT COUNT(*) FROM fact_order f
        LEFT JOIN dim_customer c ON f.customer_id = c.customer_id
        WHERE c.customer_id IS NULL
        """
    )
    bad_qty = _scalar("SELECT COUNT(*) FROM fact_order WHERE quantity <= 0")
    bad_money = _scalar(
        """
        SELECT COUNT(*) FROM fact_order
        WHERE unit_price < 0 OR gross_sales < 0 OR recognized_revenue < 0
        """
    )
    mart_mismatch = _scalar(
        """
        SELECT CASE
            WHEN (SELECT COALESCE(SUM(gross_sales), 0) FROM fact_order)
               = (SELECT COALESCE(SUM(gross_sales), 0) FROM mart_daily_sales)
            THEN 0 ELSE 1 END
        """
    )

    for name, value in [
        ("dim_customer_unique", dup_customers),
        ("fact_order_unique", dup_orders),
        ("fact_order_fk", orphan_fk),
        ("fact_order_quantity_positive", bad_qty),
        ("fact_order_money_non_negative", bad_money),
        ("mart_daily_sales_reconciles", mart_mismatch),
    ]:
        checks.append({"name": name, "passed": value == 0, "detail": f"violations={value}"})
        if value != 0:
            log_event(
                logger,
                logging.ERROR,
                f"Warehouse quality check failed: {name}",
                pipeline_stage="quality_verification",
                dataset="warehouse",
                status="failed",
                error_type="WarehouseQualityError",
            )
    return checks


def load_gold(
    *,
    db_path: Path,
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    run_record: dict[str, Any],
) -> dict[str, int]:
    """Idempotent gold load: upsert dims/facts, refresh marts, store metadata."""
    try:
        with connect(db_path) as conn:
            initialize_warehouse(conn)
            cust_n = upsert_customers(conn, customers)
            order_n = upsert_orders(conn, orders)
            mart_counts = refresh_marts(conn)
            quality = verify_warehouse_quality(conn)
            failed = [c for c in quality if not c["passed"]]
            if failed:
                raise WarehouseError(
                    f"Warehouse quality verification failed: {[c['name'] for c in failed]}"
                )
            run_record = {
                **run_record,
                "quality_checks": run_record.get("quality_checks", []) + quality,
            }
            record_run_metadata(conn, run_record)
            counts = {
                "dim_customer_upserted": cust_n,
                "fact_order_upserted": order_n,
                **mart_counts,
            }
            log_event(
                logger,
                logging.INFO,
                "Gold warehouse load complete",
                pipeline_stage="warehouse_loading",
                dataset="gold",
                row_count=order_n,
                status="ok",
            )
            return counts
    except WarehouseError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise WarehouseError("Unexpected warehouse failure") from exc

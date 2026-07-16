"""FastAPI data-serving layer over the DuckDB gold warehouse."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from pipeline.config import get_settings
from pipeline.logging_utils import configure_logging

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    warehouse_exists: bool


class RunSummary(BaseModel):
    run_id: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    input_row_counts: dict[str, Any] = Field(default_factory=dict)
    accepted_row_counts: dict[str, Any] = Field(default_factory=dict)
    rejected_row_counts: dict[str, Any] = Field(default_factory=dict)
    output_row_counts: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    is_full_load: bool | None = None


class DailySalesRow(BaseModel):
    order_date: str
    order_count: int
    units_sold: float
    gross_sales: float
    recognized_revenue: float
    avg_order_value: float


class CustomerRow(BaseModel):
    customer_id: str
    email: str
    country: str
    created_at: str
    full_name: str


class OrderRow(BaseModel):
    order_id: str
    customer_id: str
    order_ts: str
    order_date: str
    quantity: float
    unit_price: float
    currency: str
    product_sku: str
    gross_sales: float
    recognized_revenue: float


class PaginatedCustomers(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CustomerRow]


class PaginatedDailySales(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DailySalesRow]


def create_app(db_path: Path | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    warehouse = db_path or settings.duckdb_path
    assert warehouse is not None

    app = FastAPI(
        title="Global Commerce Data Platform API",
        description="Curated read API over the DuckDB analytics warehouse.",
        version="1.0.0",
    )

    @contextmanager
    def get_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
        if not warehouse.exists():
            raise HTTPException(
                status_code=503,
                detail="Warehouse not found. Run the pipeline first.",
            )
        conn = duckdb.connect(str(warehouse), read_only=True)
        try:
            yield conn
        finally:
            conn.close()

    def _parse_json_field(value: Any) -> dict[str, Any] | list[Any]:
        if value is None:
            return {}
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", warehouse_exists=warehouse.exists())

    @app.get("/runs/latest", response_model=RunSummary, tags=["ops"])
    def latest_run() -> RunSummary:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT run_id, status, CAST(started_at AS VARCHAR), CAST(completed_at AS VARCHAR),
                       input_row_counts, accepted_row_counts, rejected_row_counts,
                       output_row_counts, error_type, error_message, is_full_load
                FROM pipeline_run_metadata
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No pipeline runs recorded")
        return RunSummary(
            run_id=row[0],
            status=row[1],
            started_at=row[2],
            completed_at=row[3],
            input_row_counts=_parse_json_field(row[4]),  # type: ignore[arg-type]
            accepted_row_counts=_parse_json_field(row[5]),  # type: ignore[arg-type]
            rejected_row_counts=_parse_json_field(row[6]),  # type: ignore[arg-type]
            output_row_counts=_parse_json_field(row[7]),  # type: ignore[arg-type]
            error_type=row[8],
            error_message=row[9],
            is_full_load=bool(row[10]) if row[10] is not None else None,
        )

    @app.get("/metrics/daily-sales", response_model=PaginatedDailySales, tags=["metrics"])
    def daily_sales(
        start_date: str | None = Query(None, description="Inclusive YYYY-MM-DD"),
        end_date: str | None = Query(None, description="Inclusive YYYY-MM-DD"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> PaginatedDailySales:
        clauses: list[str] = []
        params: list[Any] = []
        if start_date:
            clauses.append("order_date >= CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            clauses.append("order_date <= CAST(? AS DATE)")
            params.append(end_date)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM mart_daily_sales {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT CAST(order_date AS VARCHAR), order_count, units_sold, gross_sales,
                       recognized_revenue, avg_order_value
                FROM mart_daily_sales
                {where}
                ORDER BY order_date
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        items = [
            DailySalesRow(
                order_date=r[0],
                order_count=int(r[1]),
                units_sold=float(r[2]),
                gross_sales=float(r[3]),
                recognized_revenue=float(r[4]),
                avg_order_value=float(r[5]),
            )
            for r in rows
        ]
        return PaginatedDailySales(total=int(total), limit=limit, offset=offset, items=items)

    @app.get("/customers", response_model=PaginatedCustomers, tags=["customers"])
    def list_customers(
        country: str | None = Query(None, description="ISO country filter"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> PaginatedCustomers:
        clauses: list[str] = []
        params: list[Any] = []
        if country:
            clauses.append("country = ?")
            params.append(country.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM dim_customer {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT customer_id, email, country, CAST(created_at AS VARCHAR), full_name
                FROM dim_customer
                {where}
                ORDER BY customer_id
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        items = [
            CustomerRow(
                customer_id=r[0],
                email=r[1],
                country=r[2],
                created_at=r[3],
                full_name=r[4],
            )
            for r in rows
        ]
        return PaginatedCustomers(total=int(total), limit=limit, offset=offset, items=items)

    @app.get("/customers/{customer_id}", response_model=CustomerRow, tags=["customers"])
    def get_customer(customer_id: str) -> CustomerRow:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT customer_id, email, country, CAST(created_at AS VARCHAR), full_name
                FROM dim_customer WHERE customer_id = ?
                """,
                [customer_id],
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        return CustomerRow(
            customer_id=row[0],
            email=row[1],
            country=row[2],
            created_at=row[3],
            full_name=row[4],
        )

    @app.get("/orders/{order_id}", response_model=OrderRow, tags=["orders"])
    def get_order(order_id: str) -> OrderRow:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT order_id, customer_id, CAST(order_ts AS VARCHAR), CAST(order_date AS VARCHAR),
                       quantity, unit_price, currency, product_sku, gross_sales, recognized_revenue
                FROM fact_order WHERE order_id = ?
                """,
                [order_id],
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
        return OrderRow(
            order_id=row[0],
            customer_id=row[1],
            order_ts=row[2],
            order_date=row[3],
            quantity=float(row[4]),
            unit_price=float(row[5]),
            currency=row[6],
            product_sku=row[7],
            gross_sales=float(row[8]),
            recognized_revenue=float(row[9]),
        )

    return app


app = create_app()

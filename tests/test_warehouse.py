"""Warehouse calculation and uniqueness tests."""

from __future__ import annotations

import duckdb

from pipeline.config import Settings
from pipeline.run import run_pipeline


def test_powerbi_view_and_uniqueness(tmp_project: Settings):
    run_pipeline(tmp_project)
    with duckdb.connect(str(tmp_project.duckdb_path)) as conn:
        dup = conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM fact_order"
        ).fetchone()[0]
        assert dup == 0
        rows = conn.execute(
            """
            SELECT order_date, customer_id, customer_country, order_count,
                   units_sold, gross_sales, recognized_revenue, average_order_value
            FROM v_powerbi_sales
            ORDER BY order_date, customer_id
            """
        ).fetchall()
        assert len(rows) >= 1
        # avg should equal gross / order_count
        for r in rows:
            order_count, gross, aov = r[3], float(r[5]), float(r[7])
            assert abs(aov - (gross / order_count)) < 1e-6

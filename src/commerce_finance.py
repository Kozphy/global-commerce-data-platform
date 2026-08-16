"""E-commerce finance and tax extension for the commerce warehouse."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import duckdb


DDL = """
CREATE TABLE IF NOT EXISTS dim_product (
    product_sku VARCHAR PRIMARY KEY,
    product_name VARCHAR NOT NULL,
    category VARCHAR,
    list_price DOUBLE NOT NULL CHECK (list_price >= 0),
    currency VARCHAR NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS fact_payment (
    payment_id VARCHAR PRIMARY KEY,
    order_id VARCHAR NOT NULL,
    payment_ts TIMESTAMP NOT NULL,
    provider VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    amount DOUBLE NOT NULL CHECK (amount >= 0),
    currency VARCHAR NOT NULL,
    provider_fee DOUBLE NOT NULL DEFAULT 0 CHECK (provider_fee >= 0)
);

CREATE TABLE IF NOT EXISTS fact_refund (
    refund_id VARCHAR PRIMARY KEY,
    order_id VARCHAR NOT NULL,
    payment_id VARCHAR,
    refund_ts TIMESTAMP NOT NULL,
    amount DOUBLE NOT NULL CHECK (amount >= 0),
    currency VARCHAR NOT NULL,
    reason VARCHAR
);

CREATE TABLE IF NOT EXISTS fact_tax (
    tax_id VARCHAR PRIMARY KEY,
    order_id VARCHAR NOT NULL,
    jurisdiction VARCHAR NOT NULL,
    tax_type VARCHAR NOT NULL,
    taxable_amount DOUBLE NOT NULL CHECK (taxable_amount >= 0),
    tax_rate DOUBLE NOT NULL CHECK (tax_rate >= 0),
    tax_amount DOUBLE NOT NULL CHECK (tax_amount >= 0),
    currency VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_fx_rate (
    rate_date DATE NOT NULL,
    base_currency VARCHAR NOT NULL,
    quote_currency VARCHAR NOT NULL,
    rate DOUBLE NOT NULL CHECK (rate > 0),
    source VARCHAR NOT NULL,
    PRIMARY KEY (rate_date, base_currency, quote_currency)
);

CREATE OR REPLACE VIEW v_order_finance_reconciliation AS
WITH payments AS (
    SELECT order_id,
           SUM(CASE WHEN lower(status) IN ('paid','captured','succeeded') THEN amount ELSE 0 END) AS paid_amount,
           SUM(provider_fee) AS payment_fees
    FROM fact_payment
    GROUP BY order_id
), refunds AS (
    SELECT order_id, SUM(amount) AS refunded_amount
    FROM fact_refund
    GROUP BY order_id
), taxes AS (
    SELECT order_id, SUM(tax_amount) AS tax_amount
    FROM fact_tax
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.currency,
    o.gross_sales,
    COALESCE(p.paid_amount, 0) AS paid_amount,
    COALESCE(r.refunded_amount, 0) AS refunded_amount,
    COALESCE(t.tax_amount, 0) AS tax_amount,
    COALESCE(p.payment_fees, 0) AS payment_fees,
    COALESCE(p.paid_amount, 0) - COALESCE(r.refunded_amount, 0) AS net_cash_collected,
    o.gross_sales + COALESCE(t.tax_amount, 0)
        - (COALESCE(p.paid_amount, 0) - COALESCE(r.refunded_amount, 0)) AS reconciliation_difference
FROM fact_order o
LEFT JOIN payments p USING (order_id)
LEFT JOIN refunds r USING (order_id)
LEFT JOIN taxes t USING (order_id);
"""


def initialize_commerce_finance(conn: duckdb.DuckDBPyConnection) -> None:
    """Create finance/tax extension tables and reconciliation view."""
    conn.execute(DDL)


def calculate_tax(taxable_amount: float, tax_rate: float) -> float:
    """Return deterministic currency-rounded tax amount."""
    if taxable_amount < 0 or tax_rate < 0:
        raise ValueError("taxable_amount and tax_rate must be non-negative")
    amount = Decimal(str(taxable_amount)) * Decimal(str(tax_rate))
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class ReconciliationResult:
    order_id: str
    gross_sales: float
    paid_amount: float
    refunded_amount: float
    tax_amount: float
    payment_fees: float
    net_cash_collected: float
    reconciliation_difference: float


def reconcile_order(conn: duckdb.DuckDBPyConnection, order_id: str) -> ReconciliationResult:
    """Read one order's finance reconciliation from the governed warehouse view."""
    row = conn.execute(
        """
        SELECT order_id, gross_sales, paid_amount, refunded_amount, tax_amount,
               payment_fees, net_cash_collected, reconciliation_difference
        FROM v_order_finance_reconciliation
        WHERE order_id = ?
        """,
        [order_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"Order {order_id} not found")
    return ReconciliationResult(
        order_id=row[0],
        gross_sales=float(row[1]),
        paid_amount=float(row[2]),
        refunded_amount=float(row[3]),
        tax_amount=float(row[4]),
        payment_fees=float(row[5]),
        net_cash_collected=float(row[6]),
        reconciliation_difference=float(row[7]),
    )


def finance_control_checks(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return auditable control checks over payments, refunds, taxes, and reconciliation."""
    checks = {
        "payments_without_order": """
            SELECT COUNT(*) FROM fact_payment p
            LEFT JOIN fact_order o ON p.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "refunds_without_order": """
            SELECT COUNT(*) FROM fact_refund r
            LEFT JOIN fact_order o ON r.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "tax_without_order": """
            SELECT COUNT(*) FROM fact_tax t
            LEFT JOIN fact_order o ON t.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "refund_exceeds_paid": """
            WITH p AS (
                SELECT order_id, SUM(amount) paid FROM fact_payment
                WHERE lower(status) IN ('paid','captured','succeeded') GROUP BY order_id
            ), r AS (
                SELECT order_id, SUM(amount) refunded FROM fact_refund GROUP BY order_id
            )
            SELECT COUNT(*) FROM r LEFT JOIN p USING (order_id)
            WHERE refunded > COALESCE(paid, 0)
        """,
    }
    results: list[dict[str, Any]] = []
    for name, sql in checks.items():
        violations = int(conn.execute(sql).fetchone()[0])
        results.append({"name": name, "passed": violations == 0, "violations": violations})
    return results

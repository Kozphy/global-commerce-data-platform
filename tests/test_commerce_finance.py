from __future__ import annotations

import duckdb
import pytest

from commerce_finance import (
    calculate_tax,
    finance_control_checks,
    initialize_commerce_finance,
    reconcile_order,
)


def _conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE fact_order (
            order_id VARCHAR PRIMARY KEY,
            customer_id VARCHAR NOT NULL,
            order_date DATE NOT NULL,
            currency VARCHAR NOT NULL,
            gross_sales DOUBLE NOT NULL
        )
        """
    )
    initialize_commerce_finance(conn)
    return conn


def test_calculate_tax_rounds_to_currency_precision() -> None:
    assert calculate_tax(100, 0.05) == 5.0
    assert calculate_tax(19.99, 0.05) == 1.0


def test_calculate_tax_rejects_negative_inputs() -> None:
    with pytest.raises(ValueError):
        calculate_tax(-1, 0.05)


def test_reconciliation_and_controls() -> None:
    conn = _conn()
    conn.execute("INSERT INTO fact_order VALUES ('O1', 'C1', DATE '2026-08-16', 'TWD', 100)")
    conn.execute(
        "INSERT INTO fact_payment VALUES ('P1','O1',current_timestamp,'demo','paid',105,'TWD',2)"
    )
    conn.execute(
        "INSERT INTO fact_tax VALUES ('T1','O1','TW','VAT',100,0.05,5,'TWD')"
    )

    result = reconcile_order(conn, "O1")
    assert result.net_cash_collected == 105.0
    assert result.tax_amount == 5.0
    assert result.payment_fees == 2.0
    assert result.reconciliation_difference == 0.0
    assert all(check["passed"] for check in finance_control_checks(conn))


def test_control_detects_refund_overpayment() -> None:
    conn = _conn()
    conn.execute("INSERT INTO fact_order VALUES ('O1', 'C1', DATE '2026-08-16', 'USD', 10)")
    conn.execute(
        "INSERT INTO fact_payment VALUES ('P1','O1',current_timestamp,'demo','paid',10,'USD',0)"
    )
    conn.execute(
        "INSERT INTO fact_refund VALUES ('R1','O1','P1',current_timestamp,12,'USD','test')"
    )
    checks = {c["name"]: c for c in finance_control_checks(conn)}
    assert checks["refund_exceeds_paid"]["passed"] is False

"""Unit tests for data-quality contracts."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.exceptions import DuplicatePrimaryKeyError, ForeignKeyViolationError
from pipeline.validate import validate_customers, validate_orders


def test_customer_required_and_email():
    df = pd.DataFrame(
        [
            {
                "customer_id": "C1",
                "email": "bad-email",
                "country": "US",
                "created_at": "2024-01-01T00:00:00Z",
                "full_name": "A",
            },
            {
                "customer_id": "C2",
                "email": "ok@example.com",
                "country": "US",
                "created_at": "2024-01-02T00:00:00Z",
                "full_name": "B",
            },
        ]
    )
    result = validate_customers(df)
    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert "email_invalid" in result.rejection_reasons[0]["reasons"]


def test_customer_duplicate_pk_fails():
    df = pd.DataFrame(
        [
            {
                "customer_id": "C1",
                "email": "a@example.com",
                "country": "US",
                "created_at": "2024-01-01T00:00:00Z",
                "full_name": "A",
            },
            {
                "customer_id": "C1",
                "email": "b@example.com",
                "country": "US",
                "created_at": "2024-01-02T00:00:00Z",
                "full_name": "B",
            },
        ]
    )
    with pytest.raises(DuplicatePrimaryKeyError):
        validate_customers(df)


def test_order_quantity_and_price_rules():
    df = pd.DataFrame(
        [
            {
                "order_id": "O1",
                "customer_id": "C1",
                "order_ts": "2024-07-01T00:00:00Z",
                "quantity": 0,
                "unit_price": 10,
                "currency": "USD",
                "product_sku": "S1",
            },
            {
                "order_id": "O2",
                "customer_id": "C1",
                "order_ts": "2024-07-01T00:00:00Z",
                "quantity": 1,
                "unit_price": -5,
                "currency": "USD",
                "product_sku": "S1",
            },
            {
                "order_id": "O3",
                "customer_id": "C1",
                "order_ts": "2024-07-01T00:00:00Z",
                "quantity": 2,
                "unit_price": 10,
                "currency": "USD",
                "product_sku": "S1",
            },
        ]
    )
    result = validate_orders(df, valid_customer_ids={"C1"})
    assert result.accepted_count == 1
    reasons = {r["record_key"]: r["reasons"] for r in result.rejection_reasons}
    assert "quantity_not_positive" in reasons["O1"]
    assert "unit_price_negative" in reasons["O2"]


def test_order_currency_and_fk():
    df = pd.DataFrame(
        [
            {
                "order_id": "O1",
                "customer_id": "MISSING",
                "order_ts": "2024-07-01T00:00:00Z",
                "quantity": 1,
                "unit_price": 10,
                "currency": "US",
                "product_sku": "S1",
            }
        ]
    )
    with pytest.raises(ForeignKeyViolationError):
        validate_orders(df, valid_customer_ids={"C1"})


def test_order_invalid_date_rejected():
    df = pd.DataFrame(
        [
            {
                "order_id": "O1",
                "customer_id": "C1",
                "order_ts": "not-a-date",
                "quantity": 1,
                "unit_price": 10,
                "currency": "USD",
                "product_sku": "S1",
            }
        ]
    )
    result = validate_orders(df, valid_customer_ids={"C1"})
    assert result.accepted_count == 0
    assert "order_ts_invalid" in result.rejection_reasons[0]["reasons"]


def test_country_empty_rejected():
    df = pd.DataFrame(
        [
            {
                "customer_id": "C1",
                "email": "a@example.com",
                "country": "   ",
                "created_at": "2024-01-01T00:00:00Z",
                "full_name": "A",
            }
        ]
    )
    result = validate_customers(df)
    assert result.accepted_count == 0

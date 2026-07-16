"""Shared pytest fixtures using temporary directories and databases."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.config import Settings


@pytest.fixture
def tmp_project(tmp_path: Path) -> Settings:
    """Isolated mini project tree with sample source data."""
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    customers = pd.DataFrame(
        [
            {
                "customer_id": "C001",
                "email": "alice@example.com",
                "country": "US",
                "created_at": "2024-01-10T08:00:00Z",
                "full_name": "Alice Chen",
            },
            {
                "customer_id": "C002",
                "email": "bob@example.com",
                "country": "GB",
                "created_at": "2024-02-15T09:30:00Z",
                "full_name": "Bob Smith",
            },
        ]
    )
    customers.to_csv(raw / "customers.csv", index=False)
    orders = [
        {
            "order_id": "O1001",
            "customer_id": "C001",
            "order_ts": "2024-07-01T10:15:00Z",
            "quantity": 2,
            "unit_price": 49.99,
            "currency": "USD",
            "product_sku": "SKU-A1",
        },
        {
            "order_id": "O1002",
            "customer_id": "C002",
            "order_ts": "2024-07-02T14:20:00Z",
            "quantity": 1,
            "unit_price": 120.0,
            "currency": "GBP",
            "product_sku": "SKU-B2",
        },
    ]
    (raw / "orders.json").write_text(json.dumps(orders), encoding="utf-8")

    return Settings(
        repo_root=tmp_path,
        raw_dir=raw,
        bronze_dir=tmp_path / "data" / "bronze",
        silver_dir=tmp_path / "data" / "silver",
        gold_dir=tmp_path / "data" / "gold",
        state_dir=tmp_path / "data" / "state",
        quality_dir=tmp_path / "data" / "quality",
        duckdb_path=tmp_path / "data" / "gold" / "commerce.duckdb",
        log_json=False,
        rest_enabled=False,
    )

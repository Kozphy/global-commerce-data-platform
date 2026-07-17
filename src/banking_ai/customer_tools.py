from __future__ import annotations

from pathlib import Path
from typing import Protocol

from banking_ai.models import CustomerFeatures


class CustomerFeatureStore(Protocol):
    def get_features(self, customer_id: str) -> CustomerFeatures: ...


class DemoCustomerFeatureStore:
    def __init__(self, features: dict[str, CustomerFeatures] | None = None) -> None:
        self.features = features or {
            "C001": CustomerFeatures(
                customer_id="C001",
                login_30d=18,
                failed_login_7d=1,
                transfers_30d=6,
                transfer_amount_24h=12000,
                product_views_30d=4,
                device_change_7d=0,
                abandonment_30d=1,
            ),
            "C002": CustomerFeatures(
                customer_id="C002",
                login_30d=9,
                failed_login_7d=4,
                transfers_30d=11,
                transfer_amount_24h=160000,
                product_views_30d=1,
                device_change_7d=1,
                abandonment_30d=3,
            ),
        }

    def get_features(self, customer_id: str) -> CustomerFeatures:
        return self.features.get(customer_id, CustomerFeatures(customer_id=customer_id))


class DuckDBCustomerFeatureStore:
    """Read-only access to the curated customer_features table."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def get_features(self, customer_id: str) -> CustomerFeatures:
        if not self.path.exists():
            return CustomerFeatures(customer_id=customer_id)
        import duckdb

        connection = duckdb.connect(str(self.path), read_only=True)
        try:
            row = connection.execute(
                """
                SELECT customer_id, login_30d, failed_login_7d, transfers_30d,
                       transfer_amount_24h, product_views_30d, device_change_7d,
                       abandonment_30d, last_event_ts
                FROM customer_features
                WHERE customer_id = ?
                """,
                [customer_id],
            ).fetchone()
        finally:
            connection.close()
        if not row:
            return CustomerFeatures(customer_id=customer_id)
        return CustomerFeatures(
            customer_id=row[0],
            login_30d=int(row[1]),
            failed_login_7d=int(row[2]),
            transfers_30d=int(row[3]),
            transfer_amount_24h=float(row[4]),
            product_views_30d=int(row[5]),
            device_change_7d=int(row[6]),
            abandonment_30d=int(row[7]),
            last_event_ts=row[8],
        )

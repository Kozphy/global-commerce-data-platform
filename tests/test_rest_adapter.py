"""REST adapter tests with mocked HTTP (no internet)."""

from __future__ import annotations

import httpx
import pytest

from pipeline.exceptions import RestIngestionError
from pipeline.ingest import RestOrdersAdapter


def test_rest_adapter_pagination_and_schema(httpx_mock=None):
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "R1",
                            "customerId": "C001",
                            "ordered_at": "2024-07-10T00:00:00Z",
                            "qty": 1,
                            "price": 9.99,
                            "currency": "USD",
                            "sku": "SKU-R",
                        }
                    ]
                },
            )
        if page == 2:
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404, json={"error": "no"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = RestOrdersAdapter(
            base_url="https://example.test",
            endpoint="/orders",
            client=client,
            max_retries=0,
        )
        df = adapter.fetch_orders(page_size=1)
    assert len(df) == 1
    assert list(df.columns) == [
        "order_id",
        "customer_id",
        "order_ts",
        "quantity",
        "unit_price",
        "currency",
        "product_sku",
    ]
    assert df.iloc[0]["order_id"] == "R1"
    assert df.iloc[0]["customer_id"] == "C001"


def test_rest_adapter_retries_then_fails():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = RestOrdersAdapter(
            base_url="https://example.test",
            endpoint="/orders",
            client=client,
            max_retries=2,
            backoff_seconds=0.01,
        )
        with pytest.raises(RestIngestionError):
            adapter.fetch_orders()
    assert calls["n"] == 3

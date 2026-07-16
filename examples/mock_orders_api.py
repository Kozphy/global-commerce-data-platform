"""Tiny local mock REST API for demonstrating REST order ingestion (no paid APIs).

Run:
  PYTHONPATH=src python examples/mock_orders_api.py

Then enable REST:
  set GCDP_REST_ENABLED=true
  PYTHONPATH=src python -m pipeline.run
"""

from __future__ import annotations

from fastapi import FastAPI, Query
import uvicorn

app = FastAPI(title="Mock Orders API")

ORDERS = [
    {
        "id": "R9001",
        "customerId": "C001",
        "ordered_at": "2024-09-01T10:00:00Z",
        "qty": 1,
        "price": 42.0,
        "currency": "USD",
        "sku": "SKU-REST",
    }
]


@app.get("/orders")
def list_orders(page: int = Query(1), page_size: int = Query(100)) -> dict:
    if page > 1:
        return {"items": []}
    return {"items": ORDERS[:page_size]}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)

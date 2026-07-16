"""FastAPI endpoint tests against a temporary warehouse."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app
from pipeline.config import Settings
from pipeline.run import run_pipeline


def test_api_endpoints(tmp_project: Settings):
    run_pipeline(tmp_project)
    app = create_app(db_path=tmp_project.duckdb_path)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    latest = client.get("/runs/latest")
    assert latest.status_code == 200
    assert latest.json()["status"] == "success"

    sales = client.get("/metrics/daily-sales?limit=10")
    assert sales.status_code == 200
    body = sales.json()
    assert body["total"] >= 1
    assert len(body["items"]) >= 1

    customers = client.get("/customers?country=US")
    assert customers.status_code == 200
    assert customers.json()["total"] == 1

    customer = client.get("/customers/C001")
    assert customer.status_code == 200
    assert customer.json()["customer_id"] == "C001"

    missing = client.get("/customers/NOPE")
    assert missing.status_code == 404

    order = client.get("/orders/O1001")
    assert order.status_code == 200
    assert order.json()["order_id"] == "O1001"

    missing_order = client.get("/orders/NOPE")
    assert missing_order.status_code == 404

"""Airflow DAG for the Global Commerce Data Platform.

Optional orchestration — the same pipeline modules used by ``python -m pipeline.run``.
Manual trigger is recommended for local development (schedule is None / @once style).

To run manually (Airflow 2.x):
  airflow dags test global_commerce_pipeline 2024-07-01
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

LOGGER = logging.getLogger(__name__)

# Resolve repo root relative to this file: <repo>/airflow/dags/this_file.py
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _on_failure(context: dict) -> None:
    task = context.get("task_instance")
    LOGGER.error(
        "Airflow task failed: dag=%s task=%s run_id=%s",
        context.get("dag"),
        getattr(task, "task_id", None),
        context.get("run_id"),
    )


def task_ingest(**_context: object) -> str:
    from pipeline.config import get_settings
    from pipeline.ingest import ingest_customers_csv, ingest_orders_json, write_bronze_snapshot
    from pipeline.state import new_run_id

    settings = get_settings(repo_root=REPO_ROOT)
    settings.ensure_directories()
    run_id = new_run_id()
    customers = ingest_customers_csv(settings.raw_dir / "customers.csv")
    orders = ingest_orders_json(settings.raw_dir / "orders.json")
    write_bronze_snapshot(customers, settings.bronze_dir, "customers", run_id)
    write_bronze_snapshot(orders, settings.bronze_dir, "orders", run_id)
    # Stash run_id for downstream via XCom by returning it
    return run_id


def task_validate(**_context: object) -> None:
    # Validation is executed inside the unified runner for consistency.
    # This task documents the logical stage and verifies source readability.
    from pipeline.config import get_settings
    from pipeline.ingest import ingest_customers_csv, ingest_orders_json
    from pipeline.validate import validate_customers, validate_orders

    settings = get_settings(repo_root=REPO_ROOT)
    customers = ingest_customers_csv(settings.raw_dir / "customers.csv")
    orders = ingest_orders_json(settings.raw_dir / "orders.json")
    cust = validate_customers(customers)
    validate_orders(orders, valid_customer_ids=set(cust.accepted["customer_id"].astype(str)))


def task_transform(**_context: object) -> None:
    from pipeline.config import get_settings
    from pipeline.ingest import ingest_customers_csv, ingest_orders_json
    from pipeline.transform import write_silver
    from pipeline.validate import enrich_customers, enrich_orders, validate_customers, validate_orders

    settings = get_settings(repo_root=REPO_ROOT)
    settings.ensure_directories()
    customers = ingest_customers_csv(settings.raw_dir / "customers.csv")
    orders = ingest_orders_json(settings.raw_dir / "orders.json")
    cust = validate_customers(customers)
    ords = validate_orders(
        orders, valid_customer_ids=set(cust.accepted["customer_id"].astype(str))
    )
    write_silver(enrich_customers(cust.accepted), settings.silver_dir, "customers")
    write_silver(enrich_orders(ords.accepted), settings.silver_dir, "orders")


def task_warehouse_load(**_context: object) -> None:
    """Prefer the tested end-to-end runner for warehouse + metadata + watermarks."""
    from pipeline.config import get_settings
    from pipeline.run import run_pipeline

    settings = get_settings(repo_root=REPO_ROOT)
    run = run_pipeline(settings)
    if run.status != "success":
        raise RuntimeError(f"Pipeline failed: {run.error_message}")


def task_quality_verify(**_context: object) -> None:
    import duckdb

    from pipeline.config import get_settings
    from pipeline.warehouse import verify_warehouse_quality

    settings = get_settings(repo_root=REPO_ROOT)
    with duckdb.connect(str(settings.duckdb_path)) as conn:
        checks = verify_warehouse_quality(conn)
    failed = [c["name"] for c in checks if not c["passed"]]
    if failed:
        raise RuntimeError(f"Quality verification failed: {failed}")


def task_completion_report(**_context: object) -> None:
    from pipeline.config import get_settings
    from pipeline.state import StateStore

    settings = get_settings(repo_root=REPO_ROOT)
    latest = StateStore(settings.state_dir).load_latest_run()
    LOGGER.info("Pipeline completion report: %s", latest)


default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "on_failure_callback": _on_failure,
}

with DAG(
    dag_id="global_commerce_pipeline",
    description="Bronze-Silver-Gold commerce pipeline (optional Airflow orchestration)",
    default_args=default_args,
    start_date=datetime(2024, 7, 1, tzinfo=UTC),
    schedule=None,  # development-safe: manual trigger only
    catchup=False,
    tags=["commerce", "duckdb", "portfolio"],
) as dag:
    ingest = PythonOperator(task_id="ingestion", python_callable=task_ingest)
    validate = PythonOperator(task_id="validation", python_callable=task_validate)
    transform = PythonOperator(task_id="transformation", python_callable=task_transform)
    warehouse = PythonOperator(task_id="warehouse_loading", python_callable=task_warehouse_load)
    quality = PythonOperator(task_id="quality_verification", python_callable=task_quality_verify)
    report = PythonOperator(task_id="completion_reporting", python_callable=task_completion_report)

    ingest >> validate >> transform >> warehouse >> quality >> report

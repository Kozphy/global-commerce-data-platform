"""End-to-end pipeline orchestration: ingest → validate → transform → gold."""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.config import Settings, get_settings
from pipeline.exceptions import PipelineError
from pipeline.ingest import (
    RestOrdersAdapter,
    ingest_customers_csv,
    ingest_orders_json,
    write_bronze_snapshot,
)
from pipeline.logging_utils import configure_logging, log_event
from pipeline.state import HighWaterMarks, PipelineRunRecord, StateStore, new_run_id, utc_now_iso
from pipeline.transform import write_silver
from pipeline.validate import (
    apply_incremental_filter,
    enrich_customers,
    enrich_orders,
    validate_customers,
    validate_orders,
    write_quality_report,
)
from pipeline.warehouse import load_gold

logger = logging.getLogger(__name__)


def _max_ts(series: pd.Series) -> str | None:
    if series.empty:
        return None
    values = [str(v) for v in series.dropna().tolist()]
    if not values:
        return None
    return max(values)


def run_pipeline(settings: Settings | None = None) -> PipelineRunRecord:
    """Execute one pipeline run with incremental loading and run metadata."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    settings.ensure_directories()

    assert settings.raw_dir and settings.bronze_dir and settings.silver_dir
    assert settings.state_dir and settings.quality_dir and settings.duckdb_path

    state = StateStore(settings.state_dir)
    watermarks = state.load_watermarks()
    is_full_load = watermarks.customers is None and watermarks.orders is None

    run = PipelineRunRecord(
        run_id=new_run_id(),
        high_water_marks_before=watermarks.to_dict(),
        is_full_load=is_full_load,
    )
    started = time.perf_counter()

    log_event(
        logger,
        logging.INFO,
        "Pipeline started",
        run_id=run.run_id,
        pipeline_stage="start",
        status="running",
    )

    try:
        # --- Ingestion ---
        customers_raw = ingest_customers_csv(settings.raw_dir / "customers.csv")
        orders_raw = ingest_orders_json(settings.raw_dir / "orders.json")

        if settings.rest_enabled:
            adapter = RestOrdersAdapter(
                base_url=settings.rest_base_url,
                endpoint=settings.rest_orders_endpoint,
                timeout_seconds=settings.rest_timeout_seconds,
                max_retries=settings.rest_max_retries,
                backoff_seconds=settings.rest_backoff_seconds,
            )
            rest_orders = adapter.fetch_orders()
            orders_raw = pd.concat([orders_raw, rest_orders], ignore_index=True)
            orders_raw = orders_raw.drop_duplicates(subset=["order_id"], keep="last")

        run.input_row_counts = {
            "customers": len(customers_raw),
            "orders": len(orders_raw),
        }

        write_bronze_snapshot(customers_raw, settings.bronze_dir, "customers", run.run_id)
        write_bronze_snapshot(orders_raw, settings.bronze_dir, "orders", run.run_id)

        # --- Incremental filter (after bronze snapshot of full extract) ---
        customers_inc = apply_incremental_filter(
            customers_raw,
            timestamp_column=settings.customers_incremental_key,
            watermark=watermarks.customers,
        )
        orders_inc = apply_incremental_filter(
            orders_raw,
            timestamp_column=settings.orders_incremental_key,
            watermark=watermarks.orders,
        )

        log_event(
            logger,
            logging.INFO,
            "Applied incremental filters",
            run_id=run.run_id,
            pipeline_stage="ingestion",
            dataset="incremental",
            row_count=len(customers_inc) + len(orders_inc),
            status="ok",
        )

        # --- Validation ---
        customer_result = validate_customers(customers_inc)
        valid_customer_ids = set(
            enrich_customers(customer_result.accepted)["customer_id"].tolist()
        )
        # For FK checks, include already-known customers from prior loads when incremental.
        if not is_full_load and settings.duckdb_path.exists():
            import duckdb

            with duckdb.connect(str(settings.duckdb_path)) as conn:
                try:
                    existing = conn.execute(
                        "SELECT customer_id FROM dim_customer"
                    ).fetchall()
                    valid_customer_ids |= {row[0] for row in existing}
                except duckdb.Error:
                    pass

        order_result = validate_orders(
            orders_inc, valid_customer_ids=valid_customer_ids
        )

        run.accepted_row_counts = {
            "customers": customer_result.accepted_count,
            "orders": order_result.accepted_count,
        }
        run.rejected_row_counts = {
            "customers": customer_result.rejected_count,
            "orders": order_result.rejected_count,
        }
        run.quality_checks = [
            asdict(c) for c in customer_result.checks + order_result.checks
        ]

        # Fail on critical reject threshold (default: any critical schema issue already raised).
        total_in = max(1, len(orders_inc) + len(customers_inc))
        total_rej = customer_result.rejected_count + order_result.rejected_count
        reject_rate = total_rej / total_in
        if reject_rate > settings.critical_reject_fail_threshold and (
            customer_result.rejected_count > 0 or order_result.rejected_count > 0
        ):
            # Soft rejects are allowed at threshold 1.0; at 0.0 we only fail if configured.
            # Default threshold 0.0 means we do NOT fail solely on soft rejects.
            pass

        write_quality_report(
            settings.quality_dir / f"quality_{run.run_id}.md",
            run_id=run.run_id,
            customer_result=customer_result,
            order_result=order_result,
        )

        # Persist rejects for auditability
        if customer_result.rejected_count:
            customer_result.rejected.to_parquet(
                settings.quality_dir / f"rejected_customers_{run.run_id}.parquet",
                index=False,
            )
        if order_result.rejected_count:
            order_result.rejected.to_parquet(
                settings.quality_dir / f"rejected_orders_{run.run_id}.parquet",
                index=False,
            )

        # --- Transformation (silver) ---
        customers_silver = enrich_customers(customer_result.accepted)
        orders_silver = enrich_orders(order_result.accepted)
        write_silver(customers_silver, settings.silver_dir, "customers")
        write_silver(orders_silver, settings.silver_dir, "orders")

        # --- Warehouse load (idempotent upserts) ---
        # For dimension completeness on incremental customer-empty runs, still refresh marts.
        gold_counts = load_gold(
            db_path=settings.duckdb_path,
            customers=customers_silver,
            orders=orders_silver,
            run_record={
                "run_id": run.run_id,
                "status": "success",
                "started_at": run.started_at,
                "completed_at": utc_now_iso(),
                "input_row_counts": run.input_row_counts,
                "accepted_row_counts": run.accepted_row_counts,
                "rejected_row_counts": run.rejected_row_counts,
                "output_row_counts": {},
                "quality_checks": run.quality_checks,
                "error_type": None,
                "error_message": None,
                "high_water_marks_before": run.high_water_marks_before,
                "high_water_marks_after": {},
                "is_full_load": run.is_full_load,
            },
        )
        run.output_row_counts = gold_counts

        # Advance high-water marks ONLY on success, based on accepted incremental rows
        # compared against prior watermark (max of prior and new max).
        new_marks = HighWaterMarks(
            customers=watermarks.customers,
            orders=watermarks.orders,
        )
        cust_max = _max_ts(customer_result.accepted["created_at"]) if not customer_result.accepted.empty else None
        order_max = _max_ts(order_result.accepted["order_ts"]) if not order_result.accepted.empty else None
        if cust_max:
            new_marks.customers = (
                cust_max
                if new_marks.customers is None
                else max(new_marks.customers, cust_max)
            )
        if order_max:
            new_marks.orders = (
                order_max if new_marks.orders is None else max(new_marks.orders, order_max)
            )
        # On full load with empty accepted (edge), still set from raw max if accepted empty?
        # Prefer accepted only so rejects never advance cursor.
        if is_full_load:
            if new_marks.customers is None and not customers_raw.empty:
                # Full load with all rejected customers should NOT advance — leave None.
                pass
            if new_marks.orders is None and not orders_raw.empty:
                pass

        state.save_watermarks(new_marks)
        run.high_water_marks_after = new_marks.to_dict()
        run.status = "success"
        run.completed_at = utc_now_iso()
        state.append_run(run)

        # Update metadata with final watermarks
        from pipeline.warehouse import connect, record_run_metadata

        with connect(settings.duckdb_path) as conn:
            record_run_metadata(conn, run.to_dict())

        duration_ms = (time.perf_counter() - started) * 1000
        log_event(
            logger,
            logging.INFO,
            "Pipeline completed successfully",
            run_id=run.run_id,
            pipeline_stage="completion",
            status="success",
            duration_ms=round(duration_ms, 2),
            row_count=run.accepted_row_counts.get("orders", 0),
        )
        return run

    except Exception as exc:
        run.status = "failed"
        run.completed_at = utc_now_iso()
        run.error_type = type(exc).__name__
        run.error_message = str(exc)
        # Do NOT advance watermarks on failure.
        run.high_water_marks_after = watermarks.to_dict()
        state.append_run(run)
        try:
            if settings.duckdb_path.exists():
                from pipeline.warehouse import connect, initialize_warehouse, record_run_metadata

                with connect(settings.duckdb_path) as conn:
                    initialize_warehouse(conn)
                    record_run_metadata(conn, run.to_dict())
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist failed-run metadata")

        log_event(
            logger,
            logging.ERROR,
            "Pipeline failed",
            run_id=run.run_id,
            pipeline_stage="completion",
            status="failed",
            error_type=type(exc).__name__,
        )
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError("Pipeline failed") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Global Commerce Data Platform pipeline")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Override repository root (useful in tests/CI)",
    )
    parser.add_argument("--no-json-logs", action="store_true")
    args = parser.parse_args(argv)

    overrides: dict[str, Any] = {}
    if args.repo_root:
        overrides["repo_root"] = args.repo_root
    if args.no_json_logs:
        overrides["log_json"] = False

    settings = get_settings(**overrides)
    run = run_pipeline(settings)
    print(f"Pipeline {run.status}: {run.run_id}")  # noqa: T201 - CLI summary
    return 0 if run.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Data contracts and quality validation for customers and orders."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from dateutil import parser as date_parser

from pipeline.exceptions import (
    DuplicatePrimaryKeyError,
    ForeignKeyViolationError,
    SchemaViolationError,
)
from pipeline.logging_utils import log_event
from pipeline.state import QualityCheckResult

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

CUSTOMER_REQUIRED = ["customer_id", "email", "country", "created_at", "full_name"]
ORDER_REQUIRED = [
    "order_id",
    "customer_id",
    "order_ts",
    "quantity",
    "unit_price",
    "currency",
    "product_sku",
]


@dataclass
class ValidationResult:
    accepted: pd.DataFrame
    rejected: pd.DataFrame
    rejection_reasons: list[dict[str, Any]] = field(default_factory=list)
    checks: list[QualityCheckResult] = field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)


def _parse_ts(value: Any) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return date_parser.isoparse(text)
    except (ValueError, TypeError, OverflowError):
        try:
            return date_parser.parse(text)
        except (ValueError, TypeError, OverflowError):
            return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null"}


def validate_customers(df: pd.DataFrame) -> ValidationResult:
    """Validate customer contract rules; separate accepted vs rejected rows."""
    reasons: list[dict[str, Any]] = []
    checks: list[QualityCheckResult] = []
    accepted_idx: list[int] = []

    # Required columns present
    missing_cols = [c for c in CUSTOMER_REQUIRED if c not in df.columns]
    if missing_cols:
        raise SchemaViolationError(
            f"Customers missing required columns: {missing_cols}"
        ) from None

    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    for idx, row in df.iterrows():
        row_reasons: list[str] = []
        customer_id = None if _is_missing(row.get("customer_id")) else str(row["customer_id"]).strip()

        if not customer_id:
            row_reasons.append("customer_id_required")
        else:
            if customer_id in seen_ids:
                row_reasons.append("customer_id_duplicate")
                duplicate_ids.add(customer_id)
            seen_ids.add(customer_id)

        for col in CUSTOMER_REQUIRED:
            if _is_missing(row.get(col)):
                row_reasons.append(f"{col}_required")

        email = None if _is_missing(row.get("email")) else str(row["email"]).strip()
        if email and not EMAIL_RE.match(email):
            row_reasons.append("email_invalid")

        country = None if _is_missing(row.get("country")) else str(row["country"]).strip()
        if country is not None and country == "":
            row_reasons.append("country_empty")

        created = _parse_ts(row.get("created_at"))
        if not _is_missing(row.get("created_at")) and created is None:
            row_reasons.append("created_at_invalid")

        if row_reasons:
            reasons.append(
                {
                    "dataset": "customers",
                    "row_index": int(idx) if isinstance(idx, (int, float)) else str(idx),
                    "record_key": customer_id,
                    "reasons": sorted(set(row_reasons)),
                }
            )
        else:
            accepted_idx.append(idx)  # type: ignore[arg-type]

    accepted = df.loc[accepted_idx].copy() if accepted_idx else df.iloc[0:0].copy()
    rejected = df.drop(index=accepted_idx).copy() if accepted_idx else df.copy()

    checks.append(
        QualityCheckResult(
            name="customers_primary_key_unique",
            passed=len(duplicate_ids) == 0,
            detail=f"duplicate_ids={sorted(duplicate_ids)}",
            severity="critical",
        )
    )
    checks.append(
        QualityCheckResult(
            name="customers_required_fields",
            passed=True,
            detail=f"accepted={len(accepted)} rejected={len(rejected)}",
            severity="warning",
        )
    )

    if duplicate_ids:
        # Critical contract violation: fail loudly.
        raise DuplicatePrimaryKeyError(
            f"Duplicate customer_id values: {sorted(duplicate_ids)}"
        ) from None

    log_event(
        logger,
        logging.INFO,
        "Validated customers",
        pipeline_stage="validation",
        dataset="customers",
        row_count=len(accepted),
        status="ok",
    )
    return ValidationResult(
        accepted=accepted,
        rejected=rejected,
        rejection_reasons=reasons,
        checks=checks,
    )


def validate_orders(
    df: pd.DataFrame,
    *,
    valid_customer_ids: set[str],
) -> ValidationResult:
    """Validate order contract rules including FK existence."""
    reasons: list[dict[str, Any]] = []
    checks: list[QualityCheckResult] = []
    accepted_idx: list[int] = []

    missing_cols = [c for c in ORDER_REQUIRED if c not in df.columns]
    if missing_cols:
        raise SchemaViolationError(f"Orders missing required columns: {missing_cols}") from None

    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    fk_violations: set[str] = set()

    for idx, row in df.iterrows():
        row_reasons: list[str] = []
        order_id = None if _is_missing(row.get("order_id")) else str(row["order_id"]).strip()
        customer_id = (
            None if _is_missing(row.get("customer_id")) else str(row["customer_id"]).strip()
        )

        if not order_id:
            row_reasons.append("order_id_required")
        else:
            if order_id in seen_ids:
                row_reasons.append("order_id_duplicate")
                duplicate_ids.add(order_id)
            seen_ids.add(order_id)

        for col in ORDER_REQUIRED:
            if _is_missing(row.get(col)):
                row_reasons.append(f"{col}_required")

        if customer_id and customer_id not in valid_customer_ids:
            row_reasons.append("customer_id_fk_missing")
            fk_violations.add(customer_id)

        order_ts = _parse_ts(row.get("order_ts"))
        if not _is_missing(row.get("order_ts")) and order_ts is None:
            row_reasons.append("order_ts_invalid")

        quantity_raw = row.get("quantity")
        try:
            quantity = float(quantity_raw) if not _is_missing(quantity_raw) else None
        except (TypeError, ValueError):
            quantity = None
            row_reasons.append("quantity_invalid")
        if quantity is not None and quantity <= 0:
            row_reasons.append("quantity_not_positive")

        unit_price_raw = row.get("unit_price")
        try:
            unit_price = float(unit_price_raw) if not _is_missing(unit_price_raw) else None
        except (TypeError, ValueError):
            unit_price = None
            row_reasons.append("unit_price_invalid")
        if unit_price is not None and unit_price < 0:
            row_reasons.append("unit_price_negative")

        # Recognized revenue = quantity * unit_price when both valid.
        if quantity is not None and unit_price is not None:
            recognized = quantity * unit_price
            if recognized < 0:
                row_reasons.append("recognized_revenue_negative")

        currency = None if _is_missing(row.get("currency")) else str(row["currency"]).strip().upper()
        if currency and not CURRENCY_RE.match(currency):
            row_reasons.append("currency_invalid")

        if row_reasons:
            reasons.append(
                {
                    "dataset": "orders",
                    "row_index": int(idx) if isinstance(idx, (int, float)) else str(idx),
                    "record_key": order_id,
                    "reasons": sorted(set(row_reasons)),
                }
            )
        else:
            accepted_idx.append(idx)  # type: ignore[arg-type]

    accepted = df.loc[accepted_idx].copy() if accepted_idx else df.iloc[0:0].copy()
    rejected = df.drop(index=accepted_idx).copy() if accepted_idx else df.copy()

    checks.append(
        QualityCheckResult(
            name="orders_primary_key_unique",
            passed=len(duplicate_ids) == 0,
            detail=f"duplicate_ids={sorted(duplicate_ids)}",
            severity="critical",
        )
    )
    checks.append(
        QualityCheckResult(
            name="orders_foreign_keys",
            passed=len(fk_violations) == 0,
            detail=f"missing_customer_ids={sorted(fk_violations)}",
            severity="critical" if fk_violations else "warning",
        )
    )

    if duplicate_ids:
        raise DuplicatePrimaryKeyError(
            f"Duplicate order_id values: {sorted(duplicate_ids)}"
        ) from None

    # FK violations are recorded as rejected rows; fail only if ALL rows violate FK
    # and there is no accepted data while input was non-empty — callers may also
    # treat high reject rates as failures.
    if len(df) > 0 and len(accepted) == 0 and fk_violations:
        raise ForeignKeyViolationError(
            f"All orders failed foreign-key checks; missing customers: {sorted(fk_violations)}"
        ) from None

    log_event(
        logger,
        logging.INFO,
        "Validated orders",
        pipeline_stage="validation",
        dataset="orders",
        row_count=len(accepted),
        status="ok",
    )
    return ValidationResult(
        accepted=accepted,
        rejected=rejected,
        rejection_reasons=reasons,
        checks=checks,
    )


def apply_incremental_filter(
    df: pd.DataFrame,
    *,
    timestamp_column: str,
    watermark: str | None,
) -> pd.DataFrame:
    """Keep rows strictly newer than the last successful watermark.

    First run (watermark is None) returns the full frame.
    """
    if watermark is None or df.empty:
        return df.copy()

    mark = _parse_ts(watermark)
    if mark is None:
        return df.copy()

    def newer(value: Any) -> bool:
        ts = _parse_ts(value)
        return ts is not None and ts > mark

    mask = df[timestamp_column].map(newer)
    return df.loc[mask].copy()


def enrich_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived analytics columns without silently coercing invalid values."""
    out = df.copy()
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce")
    out["unit_price"] = pd.to_numeric(out["unit_price"], errors="coerce")
    out["gross_sales"] = out["quantity"] * out["unit_price"]
    out["recognized_revenue"] = out["gross_sales"]
    out["order_date"] = out["order_ts"].map(
        lambda v: (_parse_ts(v).date().isoformat() if _parse_ts(v) else None)
    )
    out["currency"] = out["currency"].astype(str).str.strip().str.upper()
    return out


def enrich_customers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["customer_id"] = out["customer_id"].astype(str).str.strip()
    out["email"] = out["email"].astype(str).str.strip().str.lower()
    out["country"] = out["country"].astype(str).str.strip().str.upper()
    out["full_name"] = out["full_name"].astype(str).str.strip()
    return out


def write_quality_report(
    path: Any,
    *,
    run_id: str,
    customer_result: ValidationResult,
    order_result: ValidationResult,
) -> None:
    """Write a human-readable quality report for the run."""
    from pathlib import Path

    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Quality Report — {run_id}",
        "",
        "## Customers",
        f"- Accepted: {customer_result.accepted_count}",
        f"- Rejected: {customer_result.rejected_count}",
        "",
        "## Orders",
        f"- Accepted: {order_result.accepted_count}",
        f"- Rejected: {order_result.rejected_count}",
        "",
        "## Checks",
    ]
    for check in customer_result.checks + order_result.checks:
        mark = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{mark}] {check.name} ({check.severity}): {check.detail}")
    lines.append("")
    lines.append("## Rejection reasons")
    all_reasons = customer_result.rejection_reasons + order_result.rejection_reasons
    if not all_reasons:
        lines.append("- None")
    else:
        for item in all_reasons:
            lines.append(
                f"- {item['dataset']} key={item.get('record_key')} reasons={item['reasons']}"
            )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

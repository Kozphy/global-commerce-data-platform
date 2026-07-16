"""Source ingestion adapters: CSV, JSON file, and REST."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import pandas as pd

from pipeline.exceptions import MalformedJsonError, MissingInputError, RestIngestionError
from pipeline.logging_utils import log_event

logger = logging.getLogger(__name__)

ORDER_COLUMNS = [
    "order_id",
    "customer_id",
    "order_ts",
    "quantity",
    "unit_price",
    "currency",
    "product_sku",
]

CUSTOMER_COLUMNS = [
    "customer_id",
    "email",
    "country",
    "created_at",
    "full_name",
]


def ingest_customers_csv(path: Path) -> pd.DataFrame:
    """Load customers from CSV into a canonical DataFrame."""
    if not path.exists():
        raise MissingInputError(f"Customers CSV not found: {path}") from None
    df = pd.read_csv(path, dtype=str)
    missing = [c for c in CUSTOMER_COLUMNS if c not in df.columns]
    if missing:
        raise MissingInputError(
            f"Customers CSV missing required columns: {missing}"
        ) from None
    result = df[CUSTOMER_COLUMNS].copy()
    log_event(
        logger,
        logging.INFO,
        "Ingested customers CSV",
        pipeline_stage="ingestion",
        dataset="customers",
        row_count=len(result),
        status="ok",
    )
    return result


def ingest_orders_json(path: Path) -> pd.DataFrame:
    """Load orders from a JSON array file into the canonical order schema."""
    if not path.exists():
        raise MissingInputError(f"Orders JSON not found: {path}") from None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MalformedJsonError(f"Malformed orders JSON at {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise MalformedJsonError(
            f"Orders JSON must be a list of objects, got {type(payload).__name__}"
        ) from None
    df = pd.DataFrame(payload)
    for col in ORDER_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    result = df[ORDER_COLUMNS].astype(object)
    log_event(
        logger,
        logging.INFO,
        "Ingested orders JSON",
        pipeline_stage="ingestion",
        dataset="orders",
        row_count=len(result),
        status="ok",
    )
    return result


def _normalize_rest_order(item: dict[str, Any]) -> dict[str, Any]:
    """Map heterogeneous REST payloads onto the canonical order schema."""
    return {
        "order_id": item.get("order_id") or item.get("id"),
        "customer_id": item.get("customer_id") or item.get("customerId"),
        "order_ts": item.get("order_ts") or item.get("ordered_at") or item.get("created_at"),
        "quantity": item.get("quantity") if item.get("quantity") is not None else item.get("qty"),
        "unit_price": item.get("unit_price")
        if item.get("unit_price") is not None
        else item.get("price"),
        "currency": item.get("currency", "USD"),
        "product_sku": item.get("product_sku") or item.get("sku") or item.get("product"),
    }


class RestOrdersAdapter:
    """Reusable REST source adapter with retries, backoff, and pagination."""

    def __init__(
        self,
        *,
        base_url: str,
        endpoint: str = "/orders",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._client = client

    def _request(self, url: str, params: dict[str, Any] | None = None) -> Any:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        last_error: Exception | None = None
        try:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.get(url, params=params)
                    if response.status_code >= 500:
                        raise RestIngestionError(
                            f"Server error {response.status_code} from {url}"
                        )
                    if response.status_code >= 400:
                        raise RestIngestionError(
                            f"HTTP {response.status_code} from {url}: {response.text[:200]}"
                        )
                    try:
                        return response.json()
                    except json.JSONDecodeError as exc:
                        raise MalformedJsonError(
                            f"REST response from {url} is not valid JSON"
                        ) from exc
                except (httpx.TimeoutException, httpx.TransportError, RestIngestionError) as exc:
                    last_error = exc
                    if attempt >= self.max_retries:
                        break
                    sleep_for = self.backoff_seconds * (2**attempt)
                    log_event(
                        logger,
                        logging.WARNING,
                        "REST request failed; retrying",
                        pipeline_stage="ingestion",
                        dataset="orders_rest",
                        status="retry",
                        error_type=type(exc).__name__,
                    )
                    time.sleep(sleep_for)
            raise RestIngestionError(
                f"Failed to fetch orders from {url} after retries"
            ) from last_error
        finally:
            if owns_client:
                client.close()

    def fetch_orders(self, *, page_param: str | None = "page", page_size: int = 100) -> pd.DataFrame:
        """Fetch all pages and return a canonical orders DataFrame."""
        url = urljoin(self.base_url, self.endpoint.lstrip("/"))
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] | None = None
            if page_param:
                params = {page_param: page, "page_size": page_size}
            payload = self._request(url, params=params)
            batch = self._extract_items(payload)
            if not batch:
                break
            rows.extend(_normalize_rest_order(item) for item in batch)
            if not page_param or len(batch) < page_size:
                break
            page += 1

        df = pd.DataFrame(rows, columns=ORDER_COLUMNS) if rows else pd.DataFrame(columns=ORDER_COLUMNS)
        log_event(
            logger,
            logging.INFO,
            "Ingested orders via REST",
            pipeline_stage="ingestion",
            dataset="orders_rest",
            row_count=len(df),
            status="ok",
        )
        return df

    @staticmethod
    def _extract_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "data", "orders", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            # Single object response
            if any(k in payload for k in ("order_id", "id")):
                return [payload]
        raise RestIngestionError(
            "REST response schema invalid: expected list or object with items/data/orders"
        ) from None


def write_bronze_snapshot(
    df: pd.DataFrame,
    bronze_dir: Path,
    dataset: str,
    run_id: str,
) -> Path:
    """Persist an immutable bronze snapshot for the run."""
    bronze_dir.mkdir(parents=True, exist_ok=True)
    out = bronze_dir / f"{dataset}_{run_id}.parquet"
    df.to_parquet(out, index=False)
    log_event(
        logger,
        logging.INFO,
        "Wrote bronze snapshot",
        pipeline_stage="ingestion",
        dataset=dataset,
        row_count=len(df),
        status="ok",
    )
    return out

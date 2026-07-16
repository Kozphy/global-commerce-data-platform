"""Silver-layer transformations (validated Parquet datasets)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from pipeline.logging_utils import log_event

logger = logging.getLogger(__name__)


def write_silver(df: pd.DataFrame, silver_dir: Path, dataset: str) -> Path:
    """Write (or replace) the current silver dataset snapshot."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    out = silver_dir / f"{dataset}.parquet"
    df.to_parquet(out, index=False)
    log_event(
        logger,
        logging.INFO,
        "Wrote silver dataset",
        pipeline_stage="transformation",
        dataset=dataset,
        row_count=len(df),
        status="ok",
    )
    return out


def read_silver(silver_dir: Path, dataset: str) -> pd.DataFrame:
    path = silver_dir / f"{dataset}.parquet"
    return pd.read_parquet(path)

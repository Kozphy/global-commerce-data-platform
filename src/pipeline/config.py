from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    """Resolve repository root from this module location."""
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration for the commerce data platform."""

    model_config = SettingsConfigDict(
        env_prefix="GCDP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    repo_root: Path = _repo_root()
    raw_dir: Path | None = None
    bronze_dir: Path | None = None
    silver_dir: Path | None = None
    gold_dir: Path | None = None
    state_dir: Path | None = None
    quality_dir: Path | None = None
    duckdb_path: Path | None = None

    # Incremental watermark key for orders (ISO-8601 timestamp).
    orders_incremental_key: str = "order_ts"
    customers_incremental_key: str = "created_at"

    # REST adapter (optional; disabled by default for local demo).
    rest_enabled: bool = False
    rest_base_url: str = "http://127.0.0.1:8765"
    rest_orders_endpoint: str = "/orders"
    rest_timeout_seconds: float = 10.0
    rest_max_retries: int = 3
    rest_backoff_seconds: float = 0.5

    # Quality: fail pipeline when critical violation rate exceeds threshold.
    critical_reject_fail_threshold: float = 0.0

    log_json: bool = True
    log_level: str = "INFO"

    def model_post_init(self, __context: object) -> None:
        root = self.repo_root
        if self.raw_dir is None:
            self.raw_dir = root / "data" / "raw"
        if self.bronze_dir is None:
            self.bronze_dir = root / "data" / "bronze"
        if self.silver_dir is None:
            self.silver_dir = root / "data" / "silver"
        if self.gold_dir is None:
            self.gold_dir = root / "data" / "gold"
        if self.state_dir is None:
            self.state_dir = root / "data" / "state"
        if self.quality_dir is None:
            self.quality_dir = root / "data" / "quality"
        if self.duckdb_path is None:
            self.duckdb_path = self.gold_dir / "commerce.duckdb"

    def ensure_directories(self) -> None:
        """Create pipeline output directories if missing."""
        for path in (
            self.bronze_dir,
            self.silver_dir,
            self.gold_dir,
            self.state_dir,
            self.quality_dir,
        ):
            assert path is not None
            path.mkdir(parents=True, exist_ok=True)


def get_settings(**overrides: object) -> Settings:
    """Build settings with optional overrides (useful in tests)."""
    return Settings(**overrides)  # type: ignore[arg-type]

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from banking_ai.models import AuditRecord
from banking_ai.pii import redact


class AuditChain:
    """Append-only, PII-redacted JSONL audit chain with deterministic hashes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    def _read_raw(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def append(self, request_id: str, stage: str, payload: dict[str, Any]) -> AuditRecord:
        with self._lock:
            rows = self._read_raw()
            previous_hash = rows[-1]["record_hash"] if rows else "GENESIS"
            created_at = datetime.now(UTC)
            body = {
                "sequence": len(rows) + 1,
                "request_id": request_id,
                "stage": stage,
                "payload": redact(payload),
                "previous_hash": previous_hash,
                "created_at": created_at.isoformat(),
            }
            record_hash = hashlib.sha256(self._canonical(body).encode("utf-8")).hexdigest()
            row = {**body, "record_hash": record_hash}
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            return AuditRecord.model_validate(row)

    def for_request(self, request_id: str) -> list[AuditRecord]:
        return [
            AuditRecord.model_validate(row)
            for row in self._read_raw()
            if row.get("request_id") == request_id
        ]

    def verify(self) -> tuple[bool, int]:
        previous_hash = "GENESIS"
        rows = self._read_raw()
        for row in rows:
            claimed = row["record_hash"]
            body = {key: value for key, value in row.items() if key != "record_hash"}
            if body.get("previous_hash") != previous_hash:
                return False, int(row.get("sequence", 0))
            actual = hashlib.sha256(self._canonical(body).encode("utf-8")).hexdigest()
            if actual != claimed:
                return False, int(row.get("sequence", 0))
            previous_hash = claimed
        return True, len(rows)

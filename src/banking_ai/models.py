from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class DigitalEvent(BaseModel):
    event_id: str
    customer_id: str
    event_ts: datetime
    event_type: str
    channel: Literal["mobile", "web", "api", "branch"] = "mobile"
    session_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "customer_id", "event_type", "session_id")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class CustomerFeatures(BaseModel):
    customer_id: str
    login_30d: int = 0
    failed_login_7d: int = 0
    transfers_30d: int = 0
    transfer_amount_24h: float = 0.0
    product_views_30d: int = 0
    device_change_7d: int = 0
    abandonment_30d: int = 0
    last_event_ts: datetime | None = None


class Evidence(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    text: str
    score: float = Field(ge=0.0, le=1.0)


class AssistRequest(BaseModel):
    customer_id: str
    question: str = Field(min_length=2, max_length=4000)
    channel: Literal["mobile", "web", "contact_center"] = "mobile"
    request_id: str = Field(default_factory=lambda: str(uuid4()))


class AssistResponse(BaseModel):
    request_id: str
    status: Literal["completed", "human_review_required", "blocked"]
    intent: str
    response: str
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    customer_features: CustomerFeatures | None = None
    model_provider: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditRecord(BaseModel):
    sequence: int
    request_id: str
    stage: str
    payload: dict[str, Any]
    previous_hash: str
    record_hash: str
    created_at: datetime

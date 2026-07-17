from __future__ import annotations

import re
from typing import Any

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)\d{10,16}(?!\d)")
_TW_ID = re.compile(r"\b[A-Z][12]\d{8}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?886[- ]?)?0?9\d{2}[- ]?\d{3}[- ]?\d{3}(?!\d)")


def redact_text(value: str) -> str:
    value = _EMAIL.sub("[EMAIL_REDACTED]", value)
    value = _TW_ID.sub("[ID_REDACTED]", value)
    value = _PHONE.sub("[PHONE_REDACTED]", value)
    value = _CARD.sub("[CARD_REDACTED]", value)
    value = _ACCOUNT.sub("[ACCOUNT_REDACTED]", value)
    return value


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value

"""Structured exceptions for the commerce pipeline."""

from __future__ import annotations


class PipelineError(Exception):
    """Base error for pipeline failures."""


class MissingInputError(PipelineError):
    """Raised when a required source file is missing."""


class MalformedJsonError(PipelineError):
    """Raised when JSON source content cannot be parsed."""


class SchemaViolationError(PipelineError):
    """Raised for critical schema / contract violations."""


class InvalidDateError(PipelineError):
    """Raised when a date/timestamp field is invalid."""


class DuplicatePrimaryKeyError(PipelineError):
    """Raised when primary keys are duplicated."""


class ForeignKeyViolationError(PipelineError):
    """Raised when foreign keys do not resolve."""


class WarehouseError(PipelineError):
    """Raised when DuckDB warehouse operations fail."""


class RestIngestionError(PipelineError):
    """Raised when REST source ingestion fails."""

"""Regression coverage for the configurable soft-reject quality gate."""

import pytest

from pipeline.exceptions import PipelineError
from pipeline.run import enforce_reject_rate


@pytest.mark.parametrize(
    ("rejected", "total", "threshold"),
    [
        (0, 0, 0.0),
        (4, 10, 0.0),  # historical default: soft rejects are allowed
        (0, 0, 0.5),
        (0, 10, 0.1),
        (1, 10, 0.1),  # equality is permitted
        (1, 10, 1.0),
        (0, 0, 1.0),
    ],
)
def test_gate_allows_valid_rates(rejected, total, threshold):
    enforce_reject_rate(rejected, total, threshold)


@pytest.mark.parametrize(
    ("rejected", "total", "threshold"),
    [(2, 10, 0.1), (1, 10, 0.01), (3, 10, 0.2)],
)
def test_gate_rejects_excessive_rates(rejected, total, threshold):
    with pytest.raises(PipelineError, match="exceeds configured threshold"):
        enforce_reject_rate(rejected, total, threshold)


@pytest.mark.parametrize(
    ("rejected", "total", "threshold"),
    [(1, 1, -0.1), (1, 1, 1.1), (-1, 1, 0.2), (2, 1, 0.2)],
)
def test_gate_rejects_invalid_configuration_or_counts(rejected, total, threshold):
    with pytest.raises(ValueError):
        enforce_reject_rate(rejected, total, threshold)

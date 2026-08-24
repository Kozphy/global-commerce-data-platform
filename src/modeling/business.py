"""Translate offline recommendation quality into transparent commerce impact estimates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BusinessImpact:
    users: int
    baseline_conversion_rate: float
    model_conversion_rate: float
    average_order_value: float
    incremental_orders: float
    incremental_revenue: float
    relative_conversion_lift: float


def estimate_business_impact(
    *,
    users: int,
    baseline_conversion_rate: float,
    model_conversion_rate: float,
    average_order_value: float,
) -> BusinessImpact:
    """Estimate incremental orders/revenue from a modeled conversion-rate change.

    This is an offline scenario estimate, not a causal A/B-test claim.
    """
    if users < 0:
        raise ValueError("users must be non-negative")
    for name, value in {
        "baseline_conversion_rate": baseline_conversion_rate,
        "model_conversion_rate": model_conversion_rate,
    }.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
    if average_order_value < 0:
        raise ValueError("average_order_value must be non-negative")

    incremental_orders = users * (model_conversion_rate - baseline_conversion_rate)
    incremental_revenue = incremental_orders * average_order_value
    if baseline_conversion_rate == 0:
        relative_lift = 0.0 if model_conversion_rate == 0 else float("inf")
    else:
        relative_lift = model_conversion_rate / baseline_conversion_rate - 1.0

    return BusinessImpact(
        users=users,
        baseline_conversion_rate=baseline_conversion_rate,
        model_conversion_rate=model_conversion_rate,
        average_order_value=average_order_value,
        incremental_orders=incremental_orders,
        incremental_revenue=incremental_revenue,
        relative_conversion_lift=relative_lift,
    )

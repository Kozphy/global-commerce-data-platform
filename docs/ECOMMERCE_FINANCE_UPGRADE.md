# E-Commerce Finance & Tax Intelligence Upgrade

This branch extends the existing commerce analytics warehouse into a finance/control-oriented e-commerce platform without replacing the original Bronze-Silver-Gold pipeline.

## Added domain model

```text
Customer ──< Order >── Product
              │
              ├──< Payment
              ├──< Refund
              └──< Tax

FX Rate supports future cross-currency normalization.
```

New governed warehouse objects:

- `dim_product`
- `fact_payment`
- `fact_refund`
- `fact_tax`
- `fact_fx_rate`
- `v_order_finance_reconciliation`

## Reconciliation model

For each order the view calculates:

```text
net_cash_collected = successful_payments - refunds
reconciliation_difference = gross_sales + tax - net_cash_collected
```

Payment fees are kept separately so the model can later support PSP settlement reconciliation, contribution margin, and GL posting logic.

## Control tests

`finance_control_checks()` currently detects:

1. payments with no corresponding order
2. refunds with no corresponding order
3. tax rows with no corresponding order
4. refunds greater than successful payments

The checks return structured evidence (`name`, `passed`, `violations`) suitable for audit logs, APIs, dashboards, or human approval workflows.

## Deterministic tax calculation

`calculate_tax()` uses `Decimal` with half-up rounding to two decimal places. This is intentionally a deterministic calculation primitive, not a jurisdiction-specific tax engine. Production tax determination would require dated tax rules, nexus/registration logic, product taxability, exemptions, evidence, and jurisdictional sourcing.

## Demo

Run the existing pipeline first, then seed finance events:

```bash
PYTHONPATH=src python -m pipeline.run
PYTHONPATH=src python examples/seed_commerce_finance.py
```

The demo creates a synthetic order with payment and tax events and prints its reconciliation plus control-test results.

## Test

```bash
pytest -q tests/test_commerce_finance.py
ruff check src tests
```

## Next production-grade milestones

```text
Storefront / marketplaces
        ↓
Order + payment event ingestion
        ↓
Idempotent finance event ledger
        ↓
Tax determination + evidence
        ↓
FX normalization
        ↓
PSP / bank settlement reconciliation
        ↓
Revenue + fees + refunds + tax subledger
        ↓
GL export / journal proposal
        ↓
Human approval + immutable audit trail
        ↓
Power BI / management reporting
```

This direction turns the portfolio from a generic commerce ETL demo into a stronger **E-Commerce Finance, Tax & Control Analytics** project.
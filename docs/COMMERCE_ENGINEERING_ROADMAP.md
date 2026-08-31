# Commerce Engineering Upgrade Roadmap

## Target positioning

Evolve this repository from a portfolio ETL/ELT demo into a **Commerce + Financial Systems Data Platform** that models the complete commercial lifecycle:

```text
Customer
  -> Product / Pricing
  -> Cart / Checkout
  -> Order
  -> Payment
  -> Inventory
  -> Fulfillment / Shipment
  -> Return / Refund
  -> Reconciliation
  -> Revenue / GL
  -> Analytics / AI
  -> Audit Evidence
```

The goal is not to pretend this is a production marketplace. The goal is to demonstrate the engineering boundaries, state transitions, controls, data contracts, reconciliation logic, and observability expected in real commerce systems.

## Phase 1 — Commerce domain model

Add first-class entities:

- `product`
- `cart` / `cart_item`
- `order` / `order_line`
- `payment`
- `inventory_movement`
- `shipment`
- `refund`

Important design rule: money and inventory should be represented as explicit state transitions rather than mutable totals with no history.

Suggested order states:

```text
CREATED -> PAYMENT_PENDING -> PAID -> FULFILLING -> SHIPPED -> DELIVERED
                 |             |
                 v             v
              FAILED       CANCELLED
                                |
                                v
                             REFUNDED
```

## Phase 2 — Payment ledger

Create an append-oriented payment ledger with:

- authorization
- capture
- settlement
- refund
- chargeback
- processor fee
- currency
- provider transaction ID
- event timestamp
- idempotency key

Do not store only `payment_status` on an order. Preserve payment events so discrepancies can be reconstructed.

## Phase 3 — Reconciliation engine

Build a reconciliation pipeline:

```text
Orders
 + Payment processor settlements
 + Refunds
 + Fees
 + Bank/settlement records
        |
        v
Normalization
        |
        v
Matching engine
        |
        +--> MATCHED
        +--> AMOUNT_MISMATCH
        +--> MISSING_SETTLEMENT
        +--> ORPHAN_SETTLEMENT
        +--> DUPLICATE
        +--> LATE_SETTLEMENT
        |
        v
Exception queue
        |
        v
Human review / resolution
        |
        v
Audit evidence
```

Track metrics such as match rate, unmatched value, exception aging, duplicate rate, settlement latency, and reconciliation completeness.

## Phase 4 — Accounting / revenue bridge

Add accounting-oriented outputs rather than claiming to be a full accounting system.

Suggested tables:

- `fact_payment_event`
- `fact_refund`
- `fact_settlement`
- `fact_reconciliation_exception`
- `fact_revenue_event`
- `fact_inventory_movement`
- `bridge_order_payment`
- `mart_daily_commerce_finance`

Example lifecycle:

```text
Order created
 -> Payment captured
 -> Revenue event generated
 -> Settlement received
 -> Processor fee recognized
 -> Reconciliation completed
 -> Accounting export generated
```

The GL export should contain deterministic journal candidates with source references and audit IDs. It should not silently post accounting entries.

## Phase 5 — Event-driven architecture

Introduce domain events locally before adding real infrastructure:

```text
OrderCreated
PaymentAuthorized
PaymentCaptured
PaymentFailed
InventoryReserved
ShipmentCreated
OrderDelivered
RefundRequested
RefundCompleted
SettlementReceived
ReconciliationCompleted
```

Use an event envelope containing:

- `event_id`
- `event_type`
- `event_version`
- `aggregate_id`
- `occurred_at`
- `correlation_id`
- `causation_id`
- `idempotency_key`
- payload

A local durable event table is sufficient initially. Kafka can remain a documented future migration path until actually implemented.

## Phase 6 — Reliability and controls

Add explicit engineering controls:

- idempotent consumers
- duplicate-event detection
- retry policy
- dead-letter handling
- replay support
- schema/version compatibility
- late-arriving-event tests
- out-of-order-event tests
- invariant checks
- immutable run/event IDs

Key invariants:

```text
captured_amount >= refunded_amount
shipped_quantity <= paid/approved_quantity
settled_amount + fees approximately equals captured_amount - refunds
one provider transaction cannot settle twice without an explicit adjustment
reconciliation resolution requires evidence and actor/timestamp metadata
```

## Phase 7 — API surface

Potential endpoints:

```text
GET  /orders/{id}
GET  /orders/{id}/timeline
GET  /payments/{id}
GET  /reconciliation/exceptions
POST /reconciliation/{id}/resolve
GET  /metrics/commerce
GET  /metrics/payments
GET  /metrics/reconciliation
GET  /audit/{correlation_id}
```

Any mutating endpoint should support idempotency and record an audit event.

## Phase 8 — Analytics and decision intelligence

Gold marts can answer:

- GMV
- net revenue
- average order value
- payment authorization rate
- payment failure rate
- refund rate
- chargeback rate
- settlement latency
- reconciliation match rate
- exception aging
- inventory turnover
- customer lifetime value

Then add ML only where it has a measurable objective:

- payment failure anomaly detection
- refund-risk scoring
- demand forecasting
- inventory anomaly detection
- customer value prediction

Every model should have an offline baseline, evaluation metrics, version metadata, and human-review boundary where appropriate.

## Phase 9 — Observability

Instrument the lifecycle using structured logs and metrics keyed by `order_id`, `payment_id`, `run_id`, and `correlation_id`.

Useful operational metrics:

```text
orders_created_total
payment_capture_success_rate
payment_processing_latency
settlement_latency
reconciliation_match_rate
reconciliation_exception_count
refund_processing_latency
pipeline_freshness_seconds
data_quality_reject_rate
```

## Phase 10 — Portfolio evidence

A strong interview demonstration should prove failure handling rather than only the happy path:

1. Create an order and payment event.
2. Run the commerce pipeline.
3. Inject a settlement amount mismatch.
4. Show the reconciliation exception.
5. Resolve it through an explicit reviewed action.
6. Show the audit trail and corrected finance mart.
7. Replay the same event and demonstrate idempotency.
8. Run tests and show that accounting/reconciliation invariants remain true.

## Recommended implementation sequence

```text
1. Domain schemas + synthetic fixtures
2. Payment event ledger
3. Settlement ingestion
4. Reconciliation engine
5. Exception/audit model
6. Finance marts
7. API endpoints
8. State-transition + invariant tests
9. Observability
10. Optional ML layer
11. Optional cloud/event-bus migration
```

## Resume positioning after implementation

> Built a commerce financial data platform modeling order-to-cash workflows across orders, payments, refunds, settlements and reconciliation; implemented idempotent event processing, exception classification, audit evidence, finance marts, APIs, automated data contracts and failure-path tests.

## Architecture target

```text
Commerce Sources
      |
      v
Ingestion / Domain Events
      |
      v
Bronze immutable evidence
      |
      v
Validation + normalization
      |
      +---------------------+
      |                     |
      v                     v
Commerce facts       Payment ledger
      |                     |
      +----------+----------+
                 v
          Reconciliation
                 |
          +------+------+
          |             |
          v             v
      Exceptions    Matched records
          |             |
          +------+------+
                 v
        Revenue / GL bridge
                 |
                 v
        Gold finance marts
                 |
          +------+------+
          |             |
          v             v
       FastAPI       BI / ML
                 |
                 v
            Audit trail
```

This keeps the repository credible: implemented capabilities should be labeled implemented, and infrastructure that exists only as a migration target should remain explicitly documented as future work.

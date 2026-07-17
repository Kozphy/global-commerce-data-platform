from pathlib import Path

import duckdb

from banking_ai.audit import AuditChain
from banking_ai.cloud_models import DeterministicBankingModel
from banking_ai.customer_tools import DemoCustomerFeatureStore
from banking_ai.models import AssistRequest
from banking_ai.pii import redact_text
from banking_ai.retrieval import PolicyDocument, TfidfPolicyStore
from banking_ai.workflow import BankingAssistant
from banking_pipeline.run import build_warehouse, load_events


def build_assistant(tmp_path: Path) -> BankingAssistant:
    return BankingAssistant(
        policy_store=TfidfPolicyStore(
            [PolicyDocument("security", "Security", "Repeated failed login requires human review.")]
        ),
        feature_store=DemoCustomerFeatureStore(),
        model=DeterministicBankingModel(),
        audit=AuditChain(tmp_path / "audit.jsonl"),
    )


def test_redacts_common_pii() -> None:
    value = "Email user@example.com, card 4111 1111 1111 1111, Taiwan ID A123456789"
    redacted = redact_text(value)
    assert "user@example.com" not in redacted
    assert "4111" not in redacted
    assert "A123456789" not in redacted


def test_hash_chain_and_pii_redaction(tmp_path: Path) -> None:
    chain = AuditChain(tmp_path / "audit.jsonl")
    chain.append("r1", "received", {"email": "user@example.com"})
    chain.append("r1", "finished", {"status": "ok"})
    valid, count = chain.verify()
    assert valid is True
    assert count == 2
    assert chain.for_request("r1")[0].payload["email"] == "[EMAIL_REDACTED]"


def test_policy_retrieval_returns_relevant_chunk() -> None:
    store = TfidfPolicyStore(
        [
            PolicyDocument("security", "Security", "Repeated failed login requires identity verification."),
            PolicyDocument("loan", "Loan", "Mortgage applications need income documents."),
        ]
    )
    results = store.search("failed login verification", top_k=1)
    assert results
    assert results[0].document_id == "security"


def test_low_and_high_risk_workflow_paths(tmp_path: Path) -> None:
    assistant = build_assistant(tmp_path)
    low = assistant.run(AssistRequest(customer_id="C001", question="Why did my transfer fail?"))
    high = assistant.run(
        AssistRequest(customer_id="C002", question="My account login looks stolen")
    )
    assert low.status == "completed"
    assert low.risk_score < 0.6
    assert high.status == "human_review_required"
    assert high.risk_score >= 0.6


def test_event_pipeline_builds_customer_features(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(
        "\n".join(
            [
                '{"event_id":"1","customer_id":"C1","event_ts":"2026-07-16T00:00:00Z","event_type":"login_failed","channel":"mobile","session_id":"S1","metadata":{}}',
                '{"event_id":"2","customer_id":"C1","event_ts":"2026-07-16T00:01:00Z","event_type":"transfer_completed","channel":"mobile","session_id":"S1","metadata":{"amount":120000}}',
            ]
        ),
        encoding="utf-8",
    )
    events, rejects = load_events(source)
    assert not rejects
    database = tmp_path / "banking.duckdb"
    build_warehouse(events, database)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        row = connection.execute(
            "SELECT transfers_30d, transfer_amount_24h FROM customer_features WHERE customer_id='C1'"
        ).fetchone()
    finally:
        connection.close()
    assert row == (1, 120000.0)

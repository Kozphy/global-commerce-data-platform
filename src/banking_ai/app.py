from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from banking_ai.audit import AuditChain
from banking_ai.cloud_models import build_text_model
from banking_ai.customer_tools import DemoCustomerFeatureStore, DuckDBCustomerFeatureStore
from banking_ai.knowledge_graph import graph_payload, mermaid
from banking_ai.models import AssistRequest, AssistResponse, AuditRecord
from banking_ai.retrieval import build_policy_store, load_policy_documents
from banking_ai.workflow import BankingAssistant


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_service() -> BankingAssistant:
    root = _repo_root()
    policy_dir = Path(os.getenv("DBAI_POLICY_DIR", root / "data" / "banking_policies"))
    documents = load_policy_documents(policy_dir)
    policy_store = build_policy_store(
        documents,
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )
    db_path = Path(
        os.getenv("DBAI_DUCKDB_PATH", root / "data" / "banking_gold" / "banking.duckdb")
    )
    feature_store = (
        DuckDBCustomerFeatureStore(db_path) if db_path.exists() else DemoCustomerFeatureStore()
    )
    audit = AuditChain(
        Path(os.getenv("DBAI_AUDIT_PATH", root / "data" / "audit" / "banking_ai.jsonl"))
    )
    return BankingAssistant(
        policy_store=policy_store,
        feature_store=feature_store,
        model=build_text_model(),
        audit=audit,
    )


def create_app(service: BankingAssistant | None = None) -> FastAPI:
    service = service or build_service()
    app = FastAPI(
        title="Digital Banking AI Intelligence Platform",
        description=(
            "Auditable LangGraph, RAG, digital-trail features, MCP-ready tools, "
            "and cloud model adapters."
        ),
        version="0.1.0",
    )

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        valid, records = service.audit.verify()
        return {
            "status": "ok",
            "workflow": "langgraph" if service.graph is not None else "sequential-fallback",
            "audit_chain_valid": valid,
            "audit_records": records,
        }

    @app.post("/ai/assist", response_model=AssistResponse, tags=["ai"])
    def assist(request: AssistRequest) -> AssistResponse:
        return service.run(request)

    @app.get("/audit/{request_id}", response_model=list[AuditRecord], tags=["governance"])
    def audit_records(request_id: str) -> list[AuditRecord]:
        records = service.audit.for_request(request_id)
        if not records:
            raise HTTPException(status_code=404, detail="Request not found")
        return records

    @app.get("/architecture/graph", tags=["architecture"])
    def architecture_graph() -> dict:
        return graph_payload()

    @app.get("/architecture/mermaid", tags=["architecture"])
    def architecture_mermaid() -> dict:
        return {"mermaid": mermaid()}

    return app


app = create_app()

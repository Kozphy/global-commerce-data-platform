from __future__ import annotations

from pathlib import Path

from banking_ai.customer_tools import DemoCustomerFeatureStore, DuckDBCustomerFeatureStore
from banking_ai.retrieval import build_policy_store, load_policy_documents
from banking_ai.workflow import calculate_risk, classify_intent_text

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise RuntimeError('Install the "mcp" dependency to run the MCP server') from exc

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "banking_gold" / "banking.duckdb"
FEATURES = DuckDBCustomerFeatureStore(DB_PATH) if DB_PATH.exists() else DemoCustomerFeatureStore()
POLICIES = build_policy_store(load_policy_documents(ROOT / "data" / "banking_policies"))

mcp = FastMCP(
    "Digital Banking Intelligence",
    instructions=(
        "Read-only banking tools. Never execute transactions, reveal raw PII, or bypass human review."
    ),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def get_customer_features(customer_id: str) -> dict:
    """Return a non-PII behavioral feature summary for one synthetic/demo customer."""
    return FEATURES.get_features(customer_id).model_dump(mode="json")


@mcp.tool()
def search_bank_policy(question: str, top_k: int = 4) -> list[dict]:
    """Retrieve approved policy chunks relevant to a banking question."""
    return [item.model_dump() for item in POLICIES.search(question, top_k=top_k)]


@mcp.tool()
def assess_customer_risk(customer_id: str, question: str) -> dict:
    """Apply deterministic risk gates before an AI response is allowed."""
    intent = classify_intent_text(question)
    features = FEATURES.get_features(customer_id)
    score, flags = calculate_risk(features, intent)
    return {
        "intent": intent,
        "risk_score": score,
        "risk_flags": flags,
        "requires_human_review": score >= 0.6,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

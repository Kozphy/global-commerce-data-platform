from __future__ import annotations

from banking_ai.models import Evidence

BASE_NODES = [
    "Digital Events",
    "Bronze/Silver/Gold ETL",
    "Customer Features",
    "LangGraph Workflow",
    "Policy Vector Store",
    "Risk Gate",
    "Cloud/Local Model",
    "Human Review",
    "Audit Chain",
]

BASE_EDGES = [
    ("Digital Events", "Bronze/Silver/Gold ETL"),
    ("Bronze/Silver/Gold ETL", "Customer Features"),
    ("Customer Features", "LangGraph Workflow"),
    ("Policy Vector Store", "LangGraph Workflow"),
    ("LangGraph Workflow", "Risk Gate"),
    ("Risk Gate", "Cloud/Local Model"),
    ("Risk Gate", "Human Review"),
    ("Cloud/Local Model", "Audit Chain"),
    ("Human Review", "Audit Chain"),
]


def graph_payload(evidence: list[Evidence] | None = None) -> dict:
    nodes = [{"id": name, "type": "component"} for name in BASE_NODES]
    edges = [{"source": source, "target": target} for source, target in BASE_EDGES]
    for item in evidence or []:
        policy_id = f"policy:{item.document_id}"
        nodes.append({"id": policy_id, "type": "policy", "title": item.title})
        edges.append({"source": policy_id, "target": "Policy Vector Store"})
    return {"nodes": nodes, "edges": edges}


def mermaid() -> str:
    lines = ["flowchart LR"]
    for source, target in BASE_EDGES:
        left = source.replace(" ", "_").replace("/", "_")
        right = target.replace(" ", "_").replace("/", "_")
        lines.append(f"  {left}[{source}] --> {right}[{target}]")
    return "\n".join(lines)

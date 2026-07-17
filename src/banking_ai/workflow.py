from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict

from banking_ai.audit import AuditChain
from banking_ai.cloud_models import TextModel
from banking_ai.customer_tools import CustomerFeatureStore
from banking_ai.models import AssistRequest, AssistResponse, CustomerFeatures, Evidence
from banking_ai.pii import redact_text
from banking_ai.retrieval import PolicyStore


class WorkflowState(TypedDict, total=False):
    request_id: str
    customer_id: str
    question: str
    channel: str
    intent: str
    evidence: list[Evidence]
    customer_features: CustomerFeatures
    risk_score: float
    risk_flags: list[str]
    requires_human_review: bool
    response: str
    status: str
    model_provider: str


def classify_intent_text(question: str) -> str:
    text = question.lower()
    rules = {
        "account_security": ("locked", "login", "password", "device", "fraud", "stolen"),
        "transfer": ("transfer", "wire", "remit", "recipient", "beneficiary"),
        "card": ("card", "刷卡", "credit", "debit", "payment declined"),
        "loan": ("loan", "mortgage", "interest rate", "credit line"),
        "product": ("deposit", "investment", "insurance", "recommend"),
    }
    for intent, keywords in rules.items():
        if any(keyword in text for keyword in keywords):
            return intent
    return "general_banking"


def calculate_risk(features: CustomerFeatures, intent: str) -> tuple[float, list[str]]:
    score = 0.0
    flags: list[str] = []
    if features.failed_login_7d >= 3:
        score += 0.35
        flags.append("repeated_failed_login")
    if features.transfer_amount_24h >= 100000:
        score += 0.35
        flags.append("high_recent_transfer_amount")
    if features.device_change_7d > 0:
        score += 0.2
        flags.append("recent_device_change")
    if intent in {"account_security", "transfer"}:
        score += 0.1
        flags.append("sensitive_intent")
    return min(score, 1.0), flags


class BankingAssistant:
    def __init__(
        self,
        *,
        policy_store: PolicyStore,
        feature_store: CustomerFeatureStore,
        model: TextModel,
        audit: AuditChain,
    ) -> None:
        self.policy_store = policy_store
        self.feature_store = feature_store
        self.model = model
        self.audit = audit
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            return None

        builder = StateGraph(WorkflowState)
        builder.add_node("classify_intent", self._classify_intent)
        builder.add_node("retrieve_policy", self._retrieve_policy)
        builder.add_node("load_features", self._load_features)
        builder.add_node("risk_gate", self._risk_gate)
        builder.add_node("draft_response", self._draft_response)
        builder.add_node("human_review", self._human_review)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "classify_intent")
        builder.add_edge("classify_intent", "retrieve_policy")
        builder.add_edge("retrieve_policy", "load_features")
        builder.add_edge("load_features", "risk_gate")
        builder.add_conditional_edges(
            "risk_gate",
            self._route_after_risk,
            {"draft_response": "draft_response", "human_review": "human_review"},
        )
        builder.add_edge("draft_response", "finalize")
        builder.add_edge("human_review", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    def _classify_intent(self, state: WorkflowState) -> dict[str, Any]:
        intent = classify_intent_text(state["question"])
        self.audit.append(state["request_id"], "intent_classified", {"intent": intent})
        return {"intent": intent}

    def _retrieve_policy(self, state: WorkflowState) -> dict[str, Any]:
        evidence = self.policy_store.search(state["question"], top_k=4)
        self.audit.append(
            state["request_id"],
            "policy_retrieved",
            {"evidence_ids": [item.chunk_id for item in evidence]},
        )
        return {"evidence": evidence}

    def _load_features(self, state: WorkflowState) -> dict[str, Any]:
        features = self.feature_store.get_features(state["customer_id"])
        self.audit.append(
            state["request_id"], "customer_features_loaded", features.model_dump(mode="json")
        )
        return {"customer_features": features}

    def _risk_gate(self, state: WorkflowState) -> dict[str, Any]:
        score, flags = calculate_risk(state["customer_features"], state["intent"])
        review = score >= 0.6
        self.audit.append(
            state["request_id"],
            "risk_assessed",
            {"risk_score": score, "risk_flags": flags, "requires_human_review": review},
        )
        return {"risk_score": score, "risk_flags": flags, "requires_human_review": review}

    @staticmethod
    def _route_after_risk(state: WorkflowState) -> Literal["draft_response", "human_review"]:
        return "human_review" if state["requires_human_review"] else "draft_response"

    def _prompt(self, state: WorkflowState) -> str:
        evidence = "\n\n".join(
            f"[{item.chunk_id}] {item.text}" for item in state.get("evidence", [])
        )
        features = state["customer_features"].model_dump_json()
        return (
            "Answer using only approved policy evidence. Do not execute transactions. "
            "Do not reveal raw identifiers. State uncertainty clearly.\n\n"
            f"Intent: {state['intent']}\n"
            f"Customer feature summary: {features}\n"
            f"Question: {redact_text(state['question'])}\n\n"
            f"Approved evidence:\n{evidence}"
        )

    def _draft_response(self, state: WorkflowState) -> dict[str, Any]:
        response = self.model.generate(self._prompt(state))
        self.audit.append(
            state["request_id"],
            "response_drafted",
            {"provider": self.model.provider_name, "response": response},
        )
        return {
            "response": response,
            "status": "completed",
            "model_provider": self.model.provider_name,
        }

    def _human_review(self, state: WorkflowState) -> dict[str, Any]:
        response = (
            "For your security, this request requires review by an authorized bank specialist. "
            "No transaction or account change has been performed."
        )
        self.audit.append(
            state["request_id"],
            "human_review_requested",
            {"risk_flags": state["risk_flags"]},
        )
        return {
            "response": response,
            "status": "human_review_required",
            "model_provider": "policy-gate",
        }

    def _finalize(self, state: WorkflowState) -> dict[str, Any]:
        response = redact_text(state["response"])
        self.audit.append(state["request_id"], "finalized", {"status": state["status"]})
        return {"response": response}

    def _run_sequential(self, state: WorkflowState) -> WorkflowState:
        for node in (
            self._classify_intent,
            self._retrieve_policy,
            self._load_features,
            self._risk_gate,
        ):
            state.update(node(state))
        state.update(
            self._human_review(state)
            if state["requires_human_review"]
            else self._draft_response(state)
        )
        state.update(self._finalize(state))
        return state

    def run(self, request: AssistRequest) -> AssistResponse:
        initial: WorkflowState = {
            "request_id": request.request_id,
            "customer_id": request.customer_id,
            "question": redact_text(request.question),
            "channel": request.channel,
        }
        self.audit.append(
            request.request_id,
            "request_received",
            {
                "customer_id": request.customer_id,
                "question": request.question,
                "channel": request.channel,
            },
        )
        state = self.graph.invoke(initial) if self.graph is not None else self._run_sequential(initial)
        return AssistResponse(
            request_id=request.request_id,
            status=state["status"],
            intent=state["intent"],
            response=state["response"],
            risk_score=state["risk_score"],
            risk_flags=state["risk_flags"],
            evidence=state.get("evidence", []),
            customer_features=state.get("customer_features"),
            model_provider=state["model_provider"],
        )

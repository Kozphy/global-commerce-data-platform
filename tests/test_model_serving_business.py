from modeling.business import estimate_business_impact
from modeling.matrix_factorization import MFConfig, MatrixFactorizationRecommender
from modeling.quality_gate import evaluate_quality_gate
from modeling.registry import load_matrix_factorization, save_matrix_factorization
from modeling.serving import RecommendationService


def _trained_model():
    rows = [
        {"user_id": "u1", "item_id": "a", "rating": 5},
        {"user_id": "u1", "item_id": "b", "rating": 1},
        {"user_id": "u2", "item_id": "a", "rating": 4},
        {"user_id": "u2", "item_id": "c", "rating": 5},
        {"user_id": "u3", "item_id": "b", "rating": 5},
        {"user_id": "u3", "item_id": "c", "rating": 1},
    ]
    return MatrixFactorizationRecommender(MFConfig(factors=4, epochs=5)).fit(rows)


def test_business_impact_estimate_is_explicit_and_reproducible():
    impact = estimate_business_impact(
        users=10000,
        baseline_conversion_rate=0.03,
        model_conversion_rate=0.036,
        average_order_value=1200.0,
    )
    assert round(impact.incremental_orders, 6) == 60.0
    assert round(impact.incremental_revenue, 6) == 72000.0
    assert round(impact.relative_conversion_lift, 6) == 0.2


def test_model_registry_round_trip_and_serving_version(tmp_path):
    model = _trained_model()
    path = tmp_path / "models" / "mf-v1.json"
    saved = save_matrix_factorization(
        model,
        path,
        version="mf-v1",
        metrics={"ndcg@10": 0.42, "recall@10": 0.31},
    )
    loaded, metadata = load_matrix_factorization(path)
    assert metadata == saved
    assert loaded.predict("u1", "c") == model.predict("u1", "c")

    response = RecommendationService(loaded, metadata).recommend("u1", k=3)
    assert response.items == ["c"]
    assert response.model_version == "mf-v1"
    assert response.latency_ms >= 0.0


def test_quality_gate_blocks_metric_and_latency_regressions():
    good = evaluate_quality_gate(ndcg_at_k=0.4, recall_at_k=0.3, latency_ms=20.0)
    bad = evaluate_quality_gate(ndcg_at_k=0.01, recall_at_k=0.02, latency_ms=150.0)
    assert good.passed
    assert not bad.passed
    assert len(bad.reasons) == 3

from modeling.evaluation import ranking_metrics
from modeling.monitoring import MonitoringSnapshot, detect_drift, summarize_serving
from modeling.recommender import PopularityRecommender, UserItemRecommender


def test_popularity_recommender_excludes_seen_items():
    model = PopularityRecommender().fit([("u1", "a"), ("u2", "a"), ("u2", "b")])
    assert model.recommend("u1", k=2, seen={"a"}) == ["b"]


def test_collaborative_filtering_recommends_neighbor_item():
    interactions = [("u1", "a"), ("u1", "b"), ("u2", "a"), ("u2", "b"), ("u2", "c")]
    model = UserItemRecommender().fit(interactions)
    assert model.recommend("u1", k=1) == ["c"]


def test_ranking_metrics_are_bounded():
    metrics = ranking_metrics(["a", "b", "c"], {"b", "c"}, k=3)
    assert set(metrics) == {"precision@3", "recall@3", "ndcg@3", "mrr@3"}
    assert all(0.0 <= value <= 1.0 for value in metrics.values())


def test_monitoring_detects_runtime_and_quality_regression():
    reference = summarize_serving([0.2, 0.3], [20.0, 22.0], [False, False])
    current = MonitoringSnapshot(0.4, 40.0, 0.2)
    alerts = detect_drift(reference, current)
    assert alerts["prediction_drift"]
    assert alerts["latency_regression"]
    assert alerts["feature_quality_drift"]

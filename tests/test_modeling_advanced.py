from modeling.experiments import append_experiment, run_grid_search
from modeling.matrix_factorization import MFConfig, MatrixFactorizationRecommender
from modeling.temporal import temporal_split


def test_temporal_split_preserves_order():
    rows = [
        {"timestamp": "2024-01-03T00:00:00", "x": 3},
        {"timestamp": "2024-01-01T00:00:00", "x": 1},
        {"timestamp": "2024-01-05T00:00:00", "x": 5},
        {"timestamp": "2024-01-02T00:00:00", "x": 2},
        {"timestamp": "2024-01-04T00:00:00", "x": 4},
    ]
    split = temporal_split(rows, validation_fraction=0.2, test_fraction=0.2)
    assert [row["x"] for row in split.train] == [1, 2, 3]
    assert [row["x"] for row in split.validation] == [4]
    assert [row["x"] for row in split.test] == [5]


def test_matrix_factorization_fits_and_ranks_unseen_items():
    rows = [
        {"user_id": "u1", "item_id": "a", "rating": 5},
        {"user_id": "u1", "item_id": "b", "rating": 1},
        {"user_id": "u2", "item_id": "a", "rating": 4},
        {"user_id": "u2", "item_id": "c", "rating": 5},
        {"user_id": "u3", "item_id": "b", "rating": 5},
        {"user_id": "u3", "item_id": "c", "rating": 1},
    ]
    model = MatrixFactorizationRecommender(MFConfig(factors=4, epochs=5)).fit(rows)
    assert isinstance(model.predict("u1", "c"), float)
    assert model.recommend("u1", k=3) == ["c"]


def test_grid_search_and_experiment_log(tmp_path):
    train = [
        {"user_id": "u1", "item_id": "a", "rating": 5},
        {"user_id": "u1", "item_id": "b", "rating": 1},
        {"user_id": "u2", "item_id": "a", "rating": 4},
        {"user_id": "u2", "item_id": "c", "rating": 5},
    ]
    validation = [{"user_id": "u1", "item_id": "c", "rating": 4}]

    def evaluator(model, rows):
        error = abs(rows[0]["rating"] - model.predict(rows[0]["user_id"], rows[0]["item_id"]))
        return {"ndcg_at_k": 1.0 / (1.0 + error)}

    _, best, trials = run_grid_search(
        train,
        validation,
        evaluator,
        factors=(2, 4),
        learning_rates=(0.01,),
        regularizations=(0.01,),
        epochs=(2,),
    )
    assert len(trials) == 2
    assert best.metrics["ndcg_at_k"] >= 0

    path = tmp_path / "experiments.jsonl"
    append_experiment(best, path)
    assert '"model": "matrix_factorization"' in path.read_text(encoding="utf-8")

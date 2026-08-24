# Commerce Modeling Lifecycle

This portfolio layer demonstrates an interview-ready, reproducible recommendation workflow on top of the commerce data platform.

## Workflow

```text
Commerce interactions
    -> temporal train / validation / test split
    -> popularity and collaborative-filtering baselines
    -> matrix factorization candidate
    -> ranking / prediction evaluation
    -> deterministic hyperparameter search
    -> JSONL experiment record
    -> serving-quality monitoring
```

## Why temporal splitting matters

Recommendation systems are especially vulnerable to leakage when future interactions are allowed into training. `temporal_split` orders events by timestamp and reserves later observations for validation and test sets so evaluation better approximates deployment.

## Models

- Popularity baseline: establishes a minimum benchmark.
- User-based collaborative filtering: adds personalized neighborhood-based ranking.
- Matrix factorization: learns latent user/item vectors with SGD and explicit regularization.

The matrix-factorization implementation is intentionally small and inspectable for portfolio use. It is not presented as a distributed production recommender.

## Evaluation

The modeling package includes ranking metrics such as Precision@K, Recall@K, NDCG@K and MRR@K. The experiment runner accepts a caller-provided evaluator, allowing the objective to be tied to the relevant offline metric.

## Hyperparameter optimization

`run_grid_search` searches factor count, learning rate, regularization and epochs with deterministic seeds. Every trial captures parameters and metrics, and the selected run can be appended to a JSONL experiment ledger for reproducibility and auditability.

This is deliberately CI-friendly. A production evolution path would introduce Optuna or another search service, parallel trials, early stopping, model registry integration and richer experiment metadata.

## Lifecycle / monitoring

The repository also contains lightweight prediction, latency and feature-quality checks. Together with experiment records, tests and CI, this creates evidence for the full modeling lifecycle rather than only notebook experimentation.

## Deliberate limitations

This portfolio does not claim online A/B testing, automated retraining, production feature stores, distributed training, managed model registry, or cloud-scale serving. Those remain explicit future-work items rather than simulated production claims.

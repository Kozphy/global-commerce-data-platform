# Global Commerce Decision Science Platform

Portfolio project for **Data Scientist / Decision Science** roles in digital commerce. It combines a production-minded analytics foundation with an inspectable recommendation-modeling layer: multi-source ingestion, Bronze–Silver–Gold processing, data-quality contracts, DuckDB marts, recommendation baselines, ranking evaluation, lightweight model monitoring, FastAPI serving, Docker, tests, and CI.

> **Implemented here (local/demo):** Python pipelines, CSV/JSON/REST adapters, DuckDB, FastAPI, Airflow DAG (optional), Docker Compose, Pytest, Ruff, GitHub Actions, popularity recommendation, user-based collaborative filtering, Precision@K / Recall@K / NDCG@K / MRR@K, prediction/latency/feature-quality monitoring primitives.  
> **Not implemented:** production cloud deployment, distributed recommender training, online A/B testing, automated retraining, feature store, model registry service, Snowflake, Kafka, Spark.

---

## 1. Business problem

A fictional global commerce team needs both reliable analytics data and a reproducible foundation for customer decision models:

- Ingest customers and orders from CSV/JSON/REST sources.
- Enforce data contracts before analytics or modeling.
- Publish a star-schema warehouse for BI/API consumers.
- Support incremental loads without duplicating facts.
- Compare recommendation approaches against an explicit popularity baseline.
- Evaluate ranked recommendations with standard offline metrics.
- Detect material changes in prediction behavior, runtime latency, and feature quality.

---

## 2. Architecture

```text
CSV customers + JSON/REST orders
            ↓
Bronze immutable raw snapshots
            ↓
Incremental filter + validation
            ↓
Silver conformed datasets
            ↓
DuckDB Gold warehouse
            ↓
Feature / interaction views
            ↓
Popularity baseline ─────┐
Collaborative filtering ├─→ Ranking evaluation
                        │      Precision@K
                        │      Recall@K
                        │      NDCG@K
                        │      MRR@K
                        ↓
                 Serving / scoring
                        ↓
      Prediction + latency + feature-quality monitoring
                        ↓
               FastAPI / Power BI
```

---

## 3. Data-science layer

### Recommendation baselines

`src/modeling/recommender.py` contains two deliberately explainable baselines:

1. **PopularityRecommender** — a user-agnostic baseline that establishes the minimum bar a personalized model should beat.
2. **UserItemRecommender** — user-based collaborative filtering using cosine similarity over implicit item interactions.

The project keeps these baselines transparent because a strong Data Scientist should be able to explain *why* a more complex model is worth deploying.

### Offline evaluation

`src/modeling/evaluation.py` implements:

- Precision@K
- Recall@K
- NDCG@K
- MRR@K

These metrics make recommendation experiments comparable and prevent the portfolio from relying on vague claims such as “the model performs well.”

### Model monitoring

`src/modeling/monitoring.py` summarizes serving behavior and produces explicit alert flags for:

- prediction distribution drift
- inference latency regression
- feature missing-rate deterioration

Thresholds are configurable and intentionally simple enough to audit. This is a local demonstration of model-lifecycle thinking, **not** a claim of production MLOps infrastructure.

---

## 4. Repository structure

```text
├── airflow/dags/          # Optional Airflow orchestration
├── data/raw/              # Sample source data
├── examples/              # Mock REST API
├── src/
│   ├── api/               # FastAPI app
│   ├── modeling/          # Recommendation, evaluation, monitoring
│   └── pipeline/          # Ingest, validate, transform, warehouse, run
├── tests/                 # Data + modeling tests
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .github/workflows/ci.yml
```

---

## 5. Data flow and controls

1. Ingest customers CSV + orders JSON (optional REST merge).
2. Write immutable Bronze snapshots per `run_id`.
3. Apply incremental high-water-mark filtering.
4. Validate contracts and write rejects with reasons.
5. Publish accepted Silver Parquet datasets.
6. Upsert Gold facts/dimensions into DuckDB and rebuild marts.
7. Advance watermarks only after successful Gold loading.
8. Build interaction sets for recommendation experiments.
9. Compare personalized recommendations with the popularity baseline.
10. Record offline ranking metrics and monitor serving characteristics.

---

## 6. Existing data-engineering strengths

The platform retains the original production-minded controls:

- duplicate primary keys fail fast
- invalid rows are rejected rather than silently coerced
- failed runs do not advance watermarks
- warehouse loading is idempotent
- marts are reproducible from accepted facts
- pipeline run metadata is stored for traceability

Warehouse objects include `dim_customer`, `fact_order`, `mart_daily_sales`, `mart_customer_value`, `v_powerbi_sales`, and `pipeline_run_metadata`.

---

## 7. Experiment design

A recommended interview experiment is:

```text
Temporal train interactions
        ↓
Popularity baseline
        ↓
Collaborative-filtering candidate
        ↓
Evaluate on future held-out interactions
        ↓
Precision@K / Recall@K / NDCG@K / MRR@K
        ↓
Choose model only if it beats baseline
        ↓
Serve / monitor prediction behavior and latency
```

For a stronger future version, add matrix factorization or learning-to-rank, Optuna tuning, temporal cross-validation, experiment persistence, and confidence intervals. Those are **future work**, not currently claimed capabilities.

---

## 8. Local setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run checks:

```bash
ruff check src tests
pytest -q
PYTHONPATH=src python -m pipeline.run
```

---

## 9. Tests & CI

CI runs linting, tests, and a pipeline smoke run. Tests cover data-quality rules, idempotency, incremental loading, failed-run watermark behavior, REST mocking, API behavior, warehouse calculations, recommendation behavior, ranking-metric bounds, and monitoring alerts.

---

## 10. 90-second Data Scientist interview demo

1. Explain the business problem: reliable commerce data plus customer decision models.
2. Show Bronze → Silver → Gold and the data-quality / idempotency controls.
3. Open `src/modeling/recommender.py` and explain why popularity is the baseline.
4. Show collaborative filtering and describe the similarity assumption.
5. Open `src/modeling/evaluation.py` and explain why NDCG matters for ranked lists.
6. Run `pytest -q` to demonstrate reproducibility.
7. Show `src/modeling/monitoring.py` and explain prediction drift vs runtime regression.
8. State the limitations explicitly: local synthetic data, offline evaluation, no online A/B test or automated retraining yet.

---

## 11. Job-description mapping

| Data Scientist requirement | Evidence in this repository |
|---|---|
| Data cleansing / preprocessing | Bronze–Silver validation and reject handling |
| Feature-ready data | Gold marts / interaction-ready warehouse layer |
| Recommendation models | Popularity + user-based collaborative filtering |
| Model evaluation | Precision@K, Recall@K, NDCG@K, MRR@K |
| Iterative experimentation | Explicit baseline-versus-candidate design |
| Model lifecycle awareness | Serving metrics + drift / latency / feature-quality alerts |
| Python | Pipeline, API, modeling, testing |
| SQL | DuckDB dimensional warehouse and marts |
| E-commerce scenario | Customers, orders, customer-value and recommendation use cases |
| Runtime stability | Latency-regression monitoring primitive |

---

## 12. Known limitations

- Synthetic, small-scale portfolio data rather than real high-volume transaction logs.
- Collaborative filtering is a transparent baseline, not a state-of-the-art recommender.
- No production feature store, experiment tracker, model registry, A/B testing, or retraining orchestration.
- Single-node DuckDB rather than a multi-user cloud warehouse.
- Timestamp watermarks can miss late-arriving data.
- Airflow remains optional and is not production-hardened here.

These limitations are documented deliberately so the repository demonstrates engineering judgment rather than overstating production readiness.

---

## 13. Next upgrades

1. Add temporal train/validation/test splitting with leakage tests.
2. Add matrix factorization / implicit-feedback model.
3. Add Optuna hyperparameter optimization.
4. Persist experiment metadata and model versions.
5. Add feature-distribution metrics such as PSI / Jensen-Shannon divergence.
6. Add an offline-to-online decision document defining A/B-test guardrails.
7. Add business metrics such as revenue-per-session, conversion lift, coverage, novelty, and diversity.

---

## License

MIT (portfolio use).

# Global Commerce Data Platform

Portfolio ETL/ELT project for a **Data Engineering Intern** role: multi-source ingestion, Bronze–Silver–Gold architecture, data-quality contracts, DuckDB star-schema warehouse, FastAPI serving, optional Airflow orchestration, Docker, and CI.

> **Implemented here (local/demo):** Python pipelines, CSV/JSON/REST adapters, DuckDB, FastAPI, Airflow DAG (optional), Docker Compose, Pytest, Ruff, GitHub Actions.  
> **Not implemented (future only):** AWS/Azure/GCP production deployment, Snowflake, Kafka, Spark, managed orchestration in the cloud.

---

## 1. Business problem

A fictional global commerce team needs a reliable daily analytics foundation:

- Ingest customers (CSV) and orders (JSON, optional REST)
- Enforce data contracts before analytics
- Publish a star-schema warehouse for Power BI / API consumers
- Support **incremental** loads without duplicating facts on reruns

---

## 2. Architecture

```text
CSV customers + JSON/REST orders
            ↓
Bronze immutable raw snapshots (Parquet per run)
            ↓
Incremental filter (high-water mark) + validation
            ↓
Silver Parquet datasets
            ↓
DuckDB Gold warehouse
            ↓
dim_customer | fact_order | mart_daily_sales | mart_customer_value
            ↓
FastAPI  /  Power BI (v_powerbi_sales)
```

---

## 3. Repository structure

```text
├── airflow/dags/          # Optional Airflow DAG (calls pipeline modules)
├── data/raw/              # Source CSV + JSON (committed sample data)
├── examples/              # Mock REST API for local REST ingestion demos
├── src/
│   ├── api/               # FastAPI app
│   └── pipeline/          # Ingest, validate, transform, warehouse, run
├── tests/                 # Unit + integration tests (temp dirs/DBs)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── .github/workflows/ci.yml
```

Runtime outputs (gitignored): `data/bronze`, `data/silver`, `data/gold`, `data/state`, `data/quality`.

---

## 4. Data flow

1. **Ingest** customers CSV + orders JSON (optional REST merge)
2. **Bronze** snapshot written per `run_id`
3. **Incremental filter** keeps rows newer than last successful watermark
4. **Validate** contracts; write rejects + quality report
5. **Silver** Parquet for accepted rows
6. **Gold** upsert into DuckDB; refresh marts; store `pipeline_run_metadata`
7. **Advance watermark only on success**

---

## 5. Data contracts

### Customers

| Rule | Behavior |
|------|----------|
| `customer_id` required + unique | Duplicate PK → pipeline **fails** |
| Email plausible (`a@b.c`) | Soft reject |
| Country non-empty | Soft reject |
| `created_at` valid timestamp | Soft reject |
| Required fields present | Soft reject |

### Orders

| Rule | Behavior |
|------|----------|
| `order_id` required + unique | Duplicate PK → pipeline **fails** |
| `customer_id` exists in customers (or prior `dim_customer`) | Soft reject / fail if all rows orphaned |
| `order_ts` valid | Soft reject |
| `quantity` > 0 | Soft reject |
| `unit_price` ≥ 0 | Soft reject |
| Recognized revenue ≥ 0 | Soft reject |
| `currency` = 3-letter ISO-like code | Soft reject |

Rejected rows are written under `data/quality/` with reasons; they are **not** silently coerced.

---

## 6. Table grains

| Object | Grain |
|--------|-------|
| `dim_customer` | 1 row per `customer_id` |
| `fact_order` | 1 row per `order_id` |
| `mart_daily_sales` | 1 row per `order_date` |
| `mart_customer_value` | 1 row per `customer_id` |
| `v_powerbi_sales` | 1 row per (`order_date`, `customer_id`) |
| `pipeline_run_metadata` | 1 row per `run_id` |

---

## 7. Incremental loading design

- **Orders watermark key:** `order_ts` (ISO-8601)
- **Customers watermark key:** `created_at` (ISO-8601)
- Stored in `data/state/high_water_marks.json`
- First successful run = **full load** (empty watermarks)
- Subsequent runs process only rows **strictly newer** than the watermark
- Failed runs **do not** advance watermarks

### Limitations

- Late-arriving events with timestamps ≤ watermark are skipped
- Out-of-order source clocks can miss rows
- Soft-rejected rows never advance the cursor (by design)

---

## 8. Idempotency strategy

- Warehouse loads use `INSERT OR REPLACE` on primary keys (`customer_id`, `order_id`)
- Marts are fully rebuilt from facts each successful load
- Re-running with unchanged sources yields **zero new accepted incremental rows** and **no duplicate facts**

---

## 9. Data-quality rules

See contracts above. Each run writes:

- `data/quality/quality_<run_id>.md`
- Optional reject Parquet files
- Structured checks in run metadata + DuckDB `pipeline_run_metadata`

---

## 10. Local setup

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

---

## 11. Windows PowerShell commands

```powershell
$env:PYTHONPATH = "src"
python -m pipeline.run
python -m uvicorn api.main:app --reload --port 8000
ruff check src tests
pytest -q
```

---

## 12. macOS / Linux commands

```bash
export PYTHONPATH=src
python -m pipeline.run
python -m uvicorn api.main:app --reload --port 8000
ruff check src tests
pytest -q
```

---

## 13. Docker

```bash
docker compose run --rm pipeline
docker compose up api
```

API: http://localhost:8000/docs

**Limitation:** Airflow is not bundled in Compose (keeps the demo lightweight). Use local Airflow or skip orchestration.

---

## 14. Airflow (optional)

1. Set `AIRFLOW_HOME` and add `airflow/dags` to your DAGs folder (or symlink).
2. Ensure `PYTHONPATH` includes `src` (DAG also inserts repo `src` onto `sys.path`).
3. Trigger manually — schedule is `None` (dev-safe).

```bash
airflow dags test global_commerce_pipeline 2024-07-01
```

Logical tasks: ingestion → validation → transformation → warehouse_loading → quality_verification → completion_reporting.  
The **warehouse_loading** task runs the same tested `pipeline.run.run_pipeline` entrypoint (authoritative load + watermarks).

---

## 15. API examples

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runs/latest
curl "http://127.0.0.1:8000/metrics/daily-sales?limit=10"
curl "http://127.0.0.1:8000/customers?country=US"
curl http://127.0.0.1:8000/customers/C001
curl http://127.0.0.1:8000/orders/O1001
```

Swagger UI: `/docs`

---

## 16. REST ingestion demo (mocked, no paid API)

```bash
# Terminal 1
PYTHONPATH=src python examples/mock_orders_api.py

# Terminal 2
# PowerShell: $env:GCDP_REST_ENABLED="true"
export GCDP_REST_ENABLED=true
PYTHONPATH=src python -m pipeline.run
```

---

## 17. Tests & CI

CI (`.github/workflows/ci.yml`) runs:

```bash
ruff check src tests
pytest -q
PYTHONPATH=src python -m pipeline.run
```

Tests cover quality rules, idempotency, incremental load, failed-run watermark, mocked REST, API, and warehouse calcs — all using temporary directories/DBs.

---

## 18. Power BI connection guidance

1. Run the pipeline to create `data/gold/commerce.duckdb`
2. In Power BI Desktop, use a DuckDB connector / ODBC, **or** export:
   ```sql
   COPY (SELECT * FROM v_powerbi_sales) TO 'sales.parquet' (FORMAT PARQUET);
   ```
3. Connect to view `v_powerbi_sales` (order date, customer, country, measures)

---

## 19. Known limitations

- Single-node DuckDB file warehouse (not a multi-user cloud warehouse)
- Watermark incremental loading is timestamp-based (late data risk)
- Airflow is optional and not production-hardened in this repo
- Sample data is synthetic and small

---

## 20. Future cloud migration path (not implemented)

1. Land Bronze in object storage (S3/ADLS/GCS)
2. Orchestrate with managed Airflow / Step Functions / Composer
3. Load Gold into Snowflake / BigQuery / Redshift
4. Add schema registry + data contracts service
5. Add CDC (e.g., Debezium/Kafka) for true event-time ingestion

---

## 21. 90-second interview demo

1. Show `data/raw` sources and architecture diagram in README  
2. Run `PYTHONPATH=src python -m pipeline.run` — point at JSON logs + `run_id`  
3. Re-run — show **no duplicate** `fact_order` rows + watermark file  
4. Open DuckDB / API `/metrics/daily-sales` and `/docs`  
5. Mention tests: incremental, watermark-on-failure, REST mock, quality contracts  

---

## 22. Five likely interview questions (strong answers)

1. **Why Bronze–Silver–Gold?**  
   Bronze preserves immutable raw extracts for replay/audit; Silver holds cleaned conformed datasets; Gold is consumer-ready star schema/marts. Separation lets you reprocess without re-extracting when transforms change.

2. **How do you avoid duplicates on reruns?**  
   Natural keys with idempotent `INSERT OR REPLACE`, plus incremental watermarks so unchanged sources contribute zero new rows. Marts rebuild from facts.

3. **What happens when a run fails midway?**  
   Watermarks are advanced only after a successful gold load. Failed runs record metadata/status but leave the high-water mark unchanged so the next run reprocesses the same window.

4. **How do you validate data quality without a heavy framework?**  
   Explicit contract functions, accepted vs rejected splits, rejection reasons, critical failures (duplicate PKs), and automated tests per rule — lightweight and easy to explain in interviews.

5. **Why DuckDB here?**  
   It is an embedded analytics engine ideal for portfolio/local demos: SQL star schemas, fast Parquet I/O, zero server ops. In production you would swap the gold layer for a cloud warehouse while keeping the same dimensional model.

---

## License

MIT (portfolio use).

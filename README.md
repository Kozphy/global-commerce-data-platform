# Digital Banking AI Intelligence Platform

A portfolio-grade, local-first banking AI application that combines digital-trail ETL, customer feature engineering, LangGraph workflows, RAG, Qdrant vector retrieval, MCP tools, cloud model adapters, human review, and audit-ready evidence.

> Demo and portfolio project only. It uses synthetic data and cannot execute transactions.

## Why this project exists

It demonstrates the core capabilities requested in digital-banking AI roles:

- Python, SQL, ETL, feature engineering, and DuckDB
- LangGraph stateful workflow orchestration
- RAG over approved banking policies
- Qdrant vector database with local fallback
- MCP read-only banking tools
- AWS Bedrock Converse and Google Vertex AI adapters
- PII redaction, deterministic risk gates, human review, and audit records

## Run the demo

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src python -m banking_pipeline.run
PYTHONPATH=src uvicorn banking_ai.app:app --reload --port 8010
```

Open `http://127.0.0.1:8010/docs`.

Example:

```bash
curl -X POST http://127.0.0.1:8010/ai/assist \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C002","question":"My account login looks stolen"}'
```

The C002 example is routed to human review because the synthetic features contain repeated failed logins, a recent device change, and high transfer activity.

## Run MCP

```bash
PYTHONPATH=src python -m banking_ai.mcp_server
```

The Streamable HTTP MCP endpoint is available at `/mcp` and exposes only read-only tools.

## Optional cloud providers

```bash
pip install -e '.[cloud]'
```

AWS Bedrock:

```bash
export DBAI_MODEL_PROVIDER=bedrock
export BEDROCK_MODEL_ID=<model-id>
export AWS_REGION=<region>
```

Vertex AI uses the current Google Gen AI SDK:

```bash
export DBAI_MODEL_PROVIDER=vertex
export GOOGLE_CLOUD_PROJECT=<project>
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_GENAI_USE_VERTEXAI=True
```

Local deterministic generation is the default so the repo runs without API keys.

## Test

```bash
pytest -q
ruff check src tests
```

See `docs/DIGITAL_BANKING_ARCHITECTURE.md` for the five-repository migration map and architecture decisions.

## Legacy ETL foundation

The original commerce Bronze–Silver–Gold pipeline remains under `src/pipeline` and its tests remain active. The new `banking_pipeline` package applies the same engineering principles to digital-banking events and customer behavioral features.

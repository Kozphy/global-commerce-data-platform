FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY data/raw ./data/raw
COPY airflow ./airflow

# Create output dirs used at runtime
RUN mkdir -p data/bronze data/silver data/gold data/state data/quality

EXPOSE 8000

# Default: run API. Override command to run the pipeline.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

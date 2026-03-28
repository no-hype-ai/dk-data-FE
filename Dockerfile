# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml uv.lock* ./
COPY src/ ./src/

RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Runtime
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local

WORKDIR /app

# Bundle DrugBank seed data (tracked in Git LFS, used by seed job and MCP adapter)
COPY --chown=appuser:appuser data/drugbank/ /app/data/drugbank/

USER appuser

EXPOSE 8000

ENTRYPOINT ["uvicorn", "dk_data.ingestion.batch.api:app", "--host", "0.0.0.0", "--port", "8000"]

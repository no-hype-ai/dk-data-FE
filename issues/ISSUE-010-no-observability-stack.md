# ISSUE-010: No Observability Stack

**Project**: dk-data-FE
**Category**: Operations
**Priority**: P3 - Low
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The platform lacks a comprehensive observability stack. Health checks exist but there's no metrics collection, no distributed tracing, and logs go to stdout without aggregation. This makes debugging production issues difficult and prevents proactive monitoring.

---

## Current Observability State

| Component | Exists | Configured | Integrated |
|-----------|--------|------------|------------|
| Health endpoints | ✅ | ✅ | Partial |
| Structured logging | ❌ | ❌ | ❌ |
| Metrics (Prometheus) | ❌ | ❌ | ❌ |
| Tracing (OpenTelemetry) | ❌ | ❌ | ❌ |
| Log aggregation | ❌ | ❌ | ❌ |
| Dashboards (Grafana) | ❌ | ❌ | ❌ |
| Alerting | ❌ | ❌ | ❌ |

---

## Evidence from Codebase

### Health Checks (docker-compose.yml)

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U postgres -d edwards_tavr"]
  interval: 10s
  timeout: 5s
  retries: 5
```

**Status**: Basic liveness checks exist, but no metrics are exposed.

### Logging (base.py lines 4, 119-129)

```python
import logging
logger = logging.getLogger(__name__)

def log_fetch_result(self, result: Dict[str, Any]) -> None:
    timestamp = datetime.now().isoformat()
    if status == 'success':
        logger.info(f"[{self.SOURCE_NAME}] Fetch successful: {records} records at {timestamp}")
    else:
        logger.error(f"[{self.SOURCE_NAME}] Fetch failed: {error} at {timestamp}")
```

**Issues**:
- Unstructured log messages (string formatting)
- No correlation IDs
- No log levels from environment
- Logs to stdout only

### ARCHITECTURE.md - Future Roadmap

```markdown
## 11. Future Roadmap
8. **OpenTelemetry Integration** - Distributed tracing
```

**Status**: Acknowledged as needed but not implemented.

---

## Observability Gaps Analysis

### What You Can't See Today

| Question | Answer Capability |
|----------|-------------------|
| How many API requests per minute? | ❌ Unknown |
| What's the p99 latency for /targets? | ❌ Unknown |
| Which fetcher is taking longest? | ❌ Unknown |
| Why did the job fail at 3 AM? | ❌ Check container logs manually |
| Is database connection pooling healthy? | ❌ Unknown |
| What's the error rate trend? | ❌ Unknown |
| Which queries are slow? | ❌ Unknown without pg_stat_statements |

### Impact on Operations

```
Production Issue Occurs
        │
        ▼
┌─────────────────┐
│ User Reports    │ ← First indication of problem
│ "Scores wrong"  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ SSH into server │ ← Manual investigation
│ kubectl logs    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Search through  │ ← Hours of log reading
│ stdout logs     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Maybe find root │ ← If logs weren't rotated
│ cause           │
└─────────────────┘

Time to Resolution: Hours to Days
```

---

## Recommended Observability Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OBSERVABILITY ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   APPLICATIONS                  COLLECTORS                  BACKENDS        │
│                                                                              │
│  ┌──────────┐    metrics    ┌──────────────┐           ┌──────────────┐    │
│  │PostgREST │───────────────│              │           │  Prometheus  │    │
│  │          │               │              │──────────▶│  (metrics)   │    │
│  └──────────┘               │              │           └──────────────┘    │
│                             │              │                               │
│  ┌──────────┐    traces     │   OpenTel    │           ┌──────────────┐    │
│  │Job Trigger│──────────────│   Collector  │──────────▶│    Jaeger    │    │
│  │ (FastAPI) │              │              │           │   (traces)   │    │
│  └──────────┘               │              │           └──────────────┘    │
│                             │              │                               │
│  ┌──────────┐    logs       │              │           ┌──────────────┐    │
│  │Fetchers  │───────────────│              │──────────▶│    Loki      │    │
│  │          │               │              │           │    (logs)    │    │
│  └──────────┘               └──────────────┘           └──────────────┘    │
│                                                                 │          │
│                                                                 ▼          │
│                                                        ┌──────────────┐    │
│                                                        │   Grafana    │    │
│                                                        │ (dashboards) │    │
│                                                        └──────────────┘    │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Structured Logging

#### 1.1 Add structlog

```python
# ingestion/utils/logging.py
import structlog
import os

def configure_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()  # JSON for aggregation
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Usage
logger = structlog.get_logger()
logger.info("fetch_completed",
    source="cms_inpatient",
    records=1500,
    duration_ms=2345,
    status="success"
)
```

#### 1.2 Log Output (JSON)

```json
{
  "event": "fetch_completed",
  "source": "cms_inpatient",
  "records": 1500,
  "duration_ms": 2345,
  "status": "success",
  "timestamp": "2026-01-15T10:30:45.123Z",
  "level": "info",
  "logger": "ingestion.fetchers.cms_inpatient"
}
```

### Phase 2: Prometheus Metrics

#### 2.1 FastAPI Metrics

```python
# ingestion/batch/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
HTTP_REQUESTS = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# Job metrics
JOB_RUNS = Counter(
    'job_runs_total',
    'Total job executions',
    ['job_name', 'status']
)

JOB_DURATION = Histogram(
    'job_duration_seconds',
    'Job execution duration',
    ['job_name']
)

# Data metrics
RECORDS_INGESTED = Counter(
    'records_ingested_total',
    'Total records ingested',
    ['source']
)

DATA_FRESHNESS = Gauge(
    'data_freshness_hours',
    'Hours since last successful refresh',
    ['source']
)
```

#### 2.2 Metrics Endpoint

```python
# ingestion/batch/api.py
from prometheus_client import make_asgi_app

# Mount metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

### Phase 3: Distributed Tracing

#### 3.1 OpenTelemetry Setup

```python
# ingestion/utils/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

def configure_tracing(service_name: str):
    provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries
    FastAPIInstrumentor.instrument()
    Psycopg2Instrumentor().instrument()
    RequestsInstrumentor().instrument()

# Usage
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("fetch_cms_data") as span:
    span.set_attribute("source", "cms_inpatient")
    span.set_attribute("year", 2024)
    result = fetcher.fetch()
    span.set_attribute("records", result.get("records", 0))
```

### Phase 4: Grafana Dashboards

#### 4.1 Docker Compose Addition

```yaml
# docker-compose.observability.yml
services:
  prometheus:
    image: prom/prometheus:v2.48.0
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'

  grafana:
    image: grafana/grafana:10.2.0
    ports:
      - "3001:3000"
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}

  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  jaeger:
    image: jaegertracing/all-in-one:1.52
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC

  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.91.0
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./monitoring/otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4318:4318"  # OTLP HTTP

volumes:
  prometheus-data:
  grafana-data:
```

#### 4.2 Prometheus Configuration

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'job-trigger'
    static_configs:
      - targets: ['job-trigger:8000']

  - job_name: 'postgrest'
    static_configs:
      - targets: ['postgrest:3000']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
```

---

## Key Dashboards to Create

### Dashboard 1: API Performance

```
┌─────────────────────────────────────────────────────────┐
│ API Performance                                          │
├───────────────────┬───────────────────┬─────────────────┤
│ Requests/sec      │ Error Rate        │ p99 Latency     │
│ [42]              │ [0.5%]            │ [234ms]         │
├───────────────────┴───────────────────┴─────────────────┤
│ Request Rate by Endpoint (line chart)                    │
│ ─────────────────────────────────────────────────────── │
├─────────────────────────────────────────────────────────┤
│ Latency Distribution (heatmap)                           │
│ ░░░░▒▒▒▓▓█                                              │
└─────────────────────────────────────────────────────────┘
```

### Dashboard 2: Data Pipeline Health

```
┌─────────────────────────────────────────────────────────┐
│ Data Pipeline Health                                     │
├───────────────────┬───────────────────┬─────────────────┤
│ Last Ingestion    │ Records Today     │ Errors Today    │
│ [2 hours ago]     │ [15,420]          │ [0]             │
├─────────────────────────────────────────────────────────┤
│ Data Source Freshness (table)                            │
│ Source          │ Last Refresh  │ Status   │ Records   │
│ cms_inpatient   │ 6h ago        │ healthy  │ 12,340    │
│ cms_hospital    │ 6h ago        │ healthy  │ 4,521     │
│ hrsa            │ 30h ago       │ stale    │ 8,234     │
├─────────────────────────────────────────────────────────┤
│ Job Execution Timeline (gantt)                           │
│ ════════════════════════════════════════════════════    │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Checklist

- [ ] Add structlog for structured JSON logging
- [ ] Create prometheus_client metrics
- [ ] Add /metrics endpoint to FastAPI
- [ ] Configure OpenTelemetry tracing
- [ ] Create docker-compose.observability.yml
- [ ] Set up Prometheus scrape configs
- [ ] Create Grafana dashboards
- [ ] Configure Loki for log aggregation
- [ ] Set up Jaeger for trace viewing
- [ ] Add postgres_exporter for DB metrics
- [ ] Configure alerting rules
- [ ] Document runbooks for common alerts

---

## Quick Wins

1. **Add /metrics endpoint** (1 day)
2. **Configure structlog** (2 hours)
3. **Deploy Grafana with basic dashboard** (1 day)
4. **Add data freshness gauge** (2 hours)

---

## References

- [Prometheus: Best Practices](https://prometheus.io/docs/practices/naming/)
- [OpenTelemetry: Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [structlog: Documentation](https://www.structlog.org/)
- [Grafana: Dashboard Design](https://grafana.com/docs/grafana/latest/dashboards/)

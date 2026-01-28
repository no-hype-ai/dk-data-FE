# Data Model: Production Readiness for dk-data-fe

**Feature**: 002-production-readiness
**Date**: 2026-01-20
**Phase**: 1 (Design)

## Overview

This document defines the data models, configuration schemas, and entity relationships for the production readiness feature. The focus is on infrastructure configuration rather than application data models.

## 1. Kubernetes Resource Models

### 1.1 DopplerSecret

Synchronizes secrets from Doppler to Kubernetes Secrets.

```yaml
# Schema: secrets.doppler.com/v1alpha1/DopplerSecret
apiVersion: secrets.doppler.com/v1alpha1
kind: DopplerSecret
metadata:
  name: string        # Required: Resource name
  namespace: string   # Required: Target namespace
spec:
  tokenSecret:
    name: string      # Required: Secret containing Doppler token
  config: string      # Required: Doppler config (dev/staging/prod)
  project: string     # Required: Doppler project name
  managedSecret:
    name: string      # Required: Name of K8s Secret to create/update
    type: string      # Optional: Secret type (default: Opaque)
  resyncSeconds: int  # Optional: Sync interval (default: 60)
```

**dk-data-fe Configuration**:
| Field | Prod Value | Staging Value |
|-------|------------|---------------|
| `spec.project` | `dk-infrastructure` | `dk-infrastructure` |
| `spec.config` | `prod` | `staging` |
| `spec.resyncSeconds` | `300` | `60` |
| `spec.managedSecret.name` | `dk-data-fe-secrets` | `dk-data-fe-secrets` |

**Required Secrets in Doppler**:
| Key | Description | Used By |
|-----|-------------|---------|
| `POSTGRES_HOST` | PostgreSQL host | All services |
| `POSTGRES_PORT` | PostgreSQL port | All services |
| `POSTGRES_USER` | Database user | All services |
| `POSTGRES_PASSWORD` | Database password | All services |
| `POSTGRES_DB` | Database name | All services |
| `PGRST_JWT_SECRET` | JWT signing secret (256-bit) | PostgREST |
| `ANTHROPIC_API_KEY` | Claude API key | Enrichment service |

### 1.2 ServiceMonitor

Prometheus scrape configuration for metrics collection.

```yaml
# Schema: monitoring.coreos.com/v1/ServiceMonitor
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: string
  namespace: string
  labels:
    release: prometheus  # Required for Mimir discovery
spec:
  selector:
    matchLabels: {}      # Service labels to match
  endpoints:
    - port: string       # Named port from Service
      path: string       # Metrics path (default: /metrics)
      interval: string   # Scrape interval (default: 30s)
  namespaceSelector:
    matchNames: []       # Namespaces to watch
```

### 1.3 IngressRoute (Traefik)

External access configuration with TLS and rate limiting.

```yaml
# Schema: traefik.io/v1alpha1/IngressRoute
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: string
  namespace: string
spec:
  entryPoints:
    - websecure         # HTTPS entry point
  routes:
    - match: string     # Host/Path match rule
      kind: Rule
      services:
        - name: string  # Backend service name
          port: int     # Backend service port
      middlewares:
        - name: string  # Middleware reference
  tls:
    certResolver: string  # cert-manager resolver
```

### 1.4 NetworkPolicy

Pod-to-pod communication rules.

```yaml
# Schema: networking.k8s.io/v1/NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: string
  namespace: string
spec:
  podSelector:
    matchLabels: {}     # Pods this policy applies to
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from: []          # Allowed sources
      ports: []         # Allowed ports
  egress:
    - to: []            # Allowed destinations
      ports: []         # Allowed ports
```

## 2. Observability Configuration Models

### 2.1 OpenTelemetry Resource

Standard resource attributes for all telemetry.

```python
# Python dataclass representation
@dataclass
class OTelResource:
    service_name: str       # e.g., "dk-data-fe-postgrest"
    service_version: str    # e.g., "1.0.0"
    deployment_environment: str  # e.g., "prod", "staging"

    # Optional enrichment
    service_namespace: str = "dk-data-fe"
    host_name: str = None   # Auto-detected from K8s
```

### 2.2 Structured Log Schema

JSON log format for Loki ingestion.

```json
{
  "timestamp": "2026-01-20T10:30:00.000Z",
  "level": "INFO|WARN|ERROR|DEBUG",
  "message": "Human-readable message",
  "service": "postgrest|job-trigger|cronjob",
  "trace_id": "hex-trace-id",
  "span_id": "hex-span-id",
  "context": {
    "job_name": "cms-inpatient-fetch",
    "source_id": 12,
    "records_processed": 1500,
    "duration_ms": 3200
  }
}
```

### 2.3 Prometheus Metrics Schema

Standard metrics exposed by dk-data-fe services.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, path, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, path | Request latency |
| `db_query_duration_seconds` | Histogram | query_type | Database query time |
| `batch_job_duration_seconds` | Histogram | job_name | Job execution time |
| `batch_job_records_processed` | Counter | job_name | Records processed |
| `batch_job_failures_total` | Counter | job_name | Job failures |
| `data_source_last_refresh_timestamp` | Gauge | source_id, source_name | Last refresh time |
| `data_source_row_count` | Gauge | source_id, source_name | Current row count |

### 2.4 Alert Rule Schema

```yaml
# PrometheusRule schema
groups:
  - name: string        # Rule group name
    interval: string    # Optional: evaluation interval
    rules:
      - alert: string   # Alert name
        expr: string    # PromQL expression
        for: string     # Duration before firing
        labels:
          severity: critical|warning|info
        annotations:
          summary: string
          description: string
          runbook_url: string  # Optional
```

## 3. Application Configuration Models

### 3.1 PostgREST Configuration

Environment variables schema.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PGRST_DB_URI` | string | - | PostgreSQL connection string |
| `PGRST_DB_SCHEMAS` | string | `api` | Exposed schemas |
| `PGRST_DB_ANON_ROLE` | string | `web_anon` | Anonymous role |
| `PGRST_DB_POOL` | int | `10` | Connection pool size |
| `PGRST_JWT_SECRET` | string | - | JWT signing secret |
| `PGRST_JWT_ROLE_CLAIM_KEY` | string | `.role` | JWT role path |
| `PGRST_SERVER_HOST` | string | `0.0.0.0` | Listen address |
| `PGRST_SERVER_PORT` | int | `3000` | Listen port |
| `PGRST_MAX_ROWS` | int | `1000` | Max rows per request |
| `PGRST_LOG_LEVEL` | string | `info` | Log verbosity |

### 3.2 Job-Trigger Configuration

FastAPI service configuration.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POSTGRES_HOST` | string | - | Database host |
| `POSTGRES_PORT` | int | `5432` | Database port |
| `POSTGRES_USER` | string | - | Database user |
| `POSTGRES_PASSWORD` | string | - | Database password |
| `POSTGRES_DB` | string | - | Database name |
| `JOB_RUNNER_MODE` | string | `kubernetes` | `local` or `kubernetes` |
| `K8S_NAMESPACE` | string | - | Target namespace for jobs |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | string | - | Telemetry endpoint |
| `LOG_LEVEL` | string | `info` | Log verbosity |

### 3.3 Kustomize Overlay Model

Environment-specific configuration patches.

```yaml
# Prod overlay structure
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: dk-data-fe-prod

resources:
  - ../../base

components:
  - ../../../components/hpa-standard
  - ../../../components/pdb-standard

patches:
  - path: patches/replicas.yaml
  - path: patches/resources.yaml

configMapGenerator:
  - name: app-config
    behavior: merge
    literals:
      - LOG_LEVEL=warn

secretGenerator: []  # Secrets come from DopplerSecret
```

## 4. CI/CD Configuration Models

### 4.1 GitHub Actions Workflow Schema

```yaml
# .github/workflows/ci.yaml structure
name: CI
on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main]

jobs:
  lint:
    steps:
      - uses: actions/checkout@v4
      - run: ruff check .

  test:
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/

  security-scan:
    steps:
      - uses: actions/checkout@v4
      - uses: gitleaks/gitleaks-action@v2

  duplicate-check:
    steps:
      - uses: actions/checkout@v4
      - run: scripts/check-duplicates.sh
```

### 4.2 Gitleaks Configuration

```yaml
# .gitleaks.toml
[allowlist]
  description = "Allowed patterns"
  paths = [
    '''specs/.*\.md$''',     # Allow example secrets in specs
    '''tests/fixtures/.*''', # Allow test fixtures
  ]

[[rules]]
  id = "postgres-uri"
  description = "PostgreSQL connection string"
  regex = '''postgres://[^:]+:[^@]+@'''

[[rules]]
  id = "jwt-secret"
  description = "JWT secret"
  regex = '''PGRST_JWT_SECRET\s*=\s*["'][^"']{20,}["']'''
```

## 5. Entity Relationships

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Doppler                                    │
│                    (External Secret Store)                          │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        DopplerSecret CRD                            │
│         Syncs to: Kubernetes Secret "dk-data-fe-secrets"            │
└──────┬──────────────────────────┬──────────────────────────┬────────┘
       │                          │                          │
       ▼                          ▼                          ▼
┌──────────────┐         ┌──────────────┐          ┌──────────────┐
│  PostgREST   │         │ Job-Trigger  │          │   CronJobs   │
│  Deployment  │         │  Deployment  │          │    (K8s)     │
└──────┬───────┘         └──────┬───────┘          └──────┬───────┘
       │                        │                         │
       │                        ▼                         │
       │              ┌──────────────────┐                │
       │              │   PostgreSQL     │◄───────────────┘
       │              │    (CNPG)        │
       │              └──────────────────┘
       │
       ▼
┌──────────────────┐
│  IngressRoute    │───► External Traffic
│    (Traefik)     │
└──────────────────┘

Observability Flow:
┌──────────────────┐    ┌─────────────┐    ┌──────────────┐
│    All Pods      │───►│    Alloy    │───►│ Mimir/Loki/  │
│  (OTLP export)   │    │ (collector) │    │    Tempo     │
└──────────────────┘    └─────────────┘    └──────┬───────┘
                                                  │
                                                  ▼
                                           ┌──────────────┐
                                           │   Grafana    │
                                           │ (dashboards) │
                                           └──────────────┘
```

## 6. Migration State Machine

For tracking cleanup progress:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PENDING   │────►│ IN_PROGRESS │────►│  COMPLETED  │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   FAILED    │
                    │  (rollback) │
                    └─────────────┘
```

States for each cleanup item:
- `PENDING`: Not started
- `IN_PROGRESS`: Currently being executed
- `COMPLETED`: Successfully finished
- `FAILED`: Error occurred, requires manual intervention

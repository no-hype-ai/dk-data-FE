# Data Foundation Recommendations
## Scalable & Robust Infrastructure for Pharma Platform Behavior Labs AI

**Project**: dk-data-FE
**Assessment Date**: 2026-01-20
**Based on**: Codebase analysis + 20 open GitHub issues + dk-alchemy shared infrastructure review

---

## Executive Summary

The dk-data-FE platform provides a solid MVP foundation for TAVR data infrastructure with PostgREST API, SQLMesh transformations, and GitOps deployment.

**Key Finding**: The dk-alchemy shared infrastructure already provides many production-grade capabilities that dk-data-fe should leverage rather than rebuild. This significantly reduces the work required to achieve production readiness.

### Infrastructure Availability Matrix

| Capability | Status | Source | Action Required |
|------------|--------|--------|-----------------|
| Observability (Metrics/Logs/Traces) | ✅ Available | dk-alchemy | Instrument apps, add dashboards |
| Secrets Management | ✅ Available | dk-alchemy (Doppler) | Add secrets to Doppler project |
| PostgreSQL HA + Backups | ✅ Available | dk-alchemy (CNPG) | Use shared or create dedicated cluster |
| Redis Cache | ✅ Available | dk-alchemy | Connect to shared instance |
| Object Storage (S3) | ✅ Available | dk-alchemy (MinIO) | Use for backups/exports |
| Ingress + TLS | ✅ Available | dk-alchemy (Traefik + cert-manager) | Configure IngressRoute |
| GitOps Deployment | ✅ Available | dk-alchemy (ArgoCD) | Add bootstrap application |
| API Gateway | ⚠️ Partial | dk-alchemy (Traefik) | Add rate limiting config |
| Application Code | 🔧 Required | dk-data-fe | Security hardening, testing |

### Revised Priority Matrix

| Priority | Category | Issues | Risk Level | Effort |
|----------|----------|--------|------------|--------|
| **P0** | Security | 3 | 🔴 Critical | Low (use Doppler) |
| **P1** | Operations & Reliability | 5 | 🟠 High | **Low** (leverage dk-alchemy) |
| **P2** | Compliance & Governance | 4 | 🟡 Medium | Medium |
| **P3** | Architecture & Quality | 8 | 🟢 Low | Medium |

---

## 🏗️ dk-alchemy Integration Guide

### Available Shared Infrastructure

The dk-alchemy repository (`/Users/nicholas/Code/dk-alchemy`) provides a production-grade Kubernetes platform with:

```
dk-alchemy/
├── .gitops/                    # ArgoCD GitOps control plane
│   ├── repositories/           # Bootstrap layer (AppProjects, credentials)
│   ├── root/                   # ApplicationSets for infrastructure
│   └── external/               # External app bootstraps ← ADD dk-data-fe HERE
├── k8s/infrastructure/         # 25 core services
│   ├── postgres/               # CNPG-managed PostgreSQL (HA, backups)
│   ├── redis/                  # Redis Sentinel HA
│   ├── minio/                  # S3-compatible object storage
│   ├── grafana/                # Dashboards & visualization
│   ├── mimir/                  # Metrics storage (Prometheus-compatible)
│   ├── loki/                   # Log aggregation
│   ├── tempo/                  # Distributed tracing
│   ├── alloy/                  # OTLP telemetry collector
│   ├── doppler-operator/       # Secrets management
│   ├── cert-manager/           # TLS certificates
│   └── ...
├── k8s/components/             # Reusable Kustomize components
│   ├── hpa-standard/           # HorizontalPodAutoscaler
│   ├── pdb-standard/           # PodDisruptionBudget
│   └── otlp-collector/         # OpenTelemetry config
└── grafana/                    # GitOps-managed dashboards
    ├── dashboards/applications/  ← ADD dk-data-fe dashboards HERE
    └── alerts/                   ← ADD dk-data-fe alerts HERE
```

### Step 1: Add dk-data-fe to ArgoCD

Create bootstrap application in dk-alchemy:

```yaml
# dk-alchemy/.gitops/external/dk-data-fe.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dk-data-fe-bootstrap-prod
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: dk-data-fe-bootstrap
  source:
    repoURL: https://github.com/data-kinetic/dk-data-fe.git
    targetRevision: main
    path: .gitops/prod/apps
    directory:
      recurse: false
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dk-data-fe-bootstrap-staging
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: dk-data-fe-bootstrap
  source:
    repoURL: https://github.com/data-kinetic/dk-data-fe.git
    targetRevision: staging
    path: .gitops/staging/apps
    directory:
      recurse: false
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

Create AppProject for permissions:

```yaml
# dk-alchemy/.gitops/repositories/dk-data-fe-bootstrap-project.yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: dk-data-fe-bootstrap
  namespace: argocd
spec:
  description: dk-data-fe data platform bootstrap
  sourceRepos:
    - https://github.com/data-kinetic/dk-data-fe.git
  destinations:
    - namespace: argocd
      server: https://kubernetes.default.svc
    - namespace: dk-data-fe-prod
      server: https://kubernetes.default.svc
    - namespace: dk-data-fe-staging
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: ''
      kind: Namespace
  namespaceResourceWhitelist:
    - group: argoproj.io
      kind: Application
    - group: argoproj.io
      kind: AppProject
    - group: '*'
      kind: '*'
```

### Step 2: Create dk-data-fe GitOps Structure

Restructure dk-data-fe to follow dk-alchemy patterns:

```
dk-data-fe/
├── .gitops/
│   ├── prod/
│   │   └── apps/
│   │       ├── kustomization.yaml
│   │       ├── namespace.yaml
│   │       ├── postgrest-app.yaml      # ArgoCD Application
│   │       ├── job-trigger-app.yaml    # ArgoCD Application
│   │       └── cronjobs-app.yaml       # ArgoCD Application
│   └── staging/
│       └── apps/
│           └── ... (same structure, smaller resources)
├── k8s/
│   ├── postgrest/
│   │   ├── base/
│   │   │   ├── kustomization.yaml
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   └── configmap.yaml
│   │   └── overlays/
│   │       ├── prod/kustomization.yaml
│   │       └── staging/kustomization.yaml
│   ├── job-trigger/
│   │   └── ... (same pattern)
│   └── cronjobs/
│       └── ... (same pattern)
└── src/dk_data/
    └── ... (application code)
```

### Step 3: Configure Secrets via Doppler

Add dk-data-fe secrets to the `dk-infrastructure` Doppler project:

```bash
# Required secrets for dk-data-fe
POSTGRES_PASSWORD=<generated>
POSTGREST_JWT_SECRET=<256-bit-base64>
POSTGREST_AUTHENTICATOR_PASSWORD=<generated>
```

Create DopplerSecret in dk-data-fe namespace:

```yaml
# k8s/postgrest/base/doppler-secret.yaml
apiVersion: secrets.doppler.com/v1alpha1
kind: DopplerSecret
metadata:
  name: dk-data-fe-secrets
  namespace: dk-data-fe-prod
spec:
  tokenSecret:
    name: doppler-token-dk-infrastructure
  managedSecret:
    name: dk-data-fe-secrets
    type: Opaque
  config: prod  # or staging
  project: dk-infrastructure
```

### Step 4: Connect to Shared Services

**PostgreSQL Connection**:
```yaml
# Option A: Use shared cluster
POSTGRES_HOST: postgres-rw.infra.svc.cluster.local
POSTGRES_PORT: "5432"
POSTGRES_DB: dk_data_fe  # Request database creation

# Option B: Dedicated CNPG cluster (recommended for isolation)
# Create via CNPG Cluster CRD in dk-data-fe namespace
```

**Redis Connection** (for caching):
```yaml
REDIS_HOST: redis-master.infra.svc.cluster.local
REDIS_PORT: "6379"
```

**MinIO Connection** (for backups/exports):
```yaml
S3_ENDPOINT: http://minio.infra.svc.cluster.local:9000
S3_BUCKET: dk-data-fe-backups
```

### Step 5: Instrument for Observability

The dk-alchemy observability stack uses:
- **Alloy** (DaemonSet) - Collects OTLP telemetry
- **Mimir** - Prometheus-compatible metrics
- **Loki** - Log aggregation
- **Tempo** - Distributed tracing

**Python instrumentation**:
```python
# src/dk_data/observability.py
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
import structlog

# Configure OTLP export to Alloy
resource = Resource.create({"service.name": "dk-data-fe"})

# Tracing
trace.set_tracer_provider(TracerProvider(resource=resource))
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="alloy.infra.svc.cluster.local:4317"))
)

# Metrics
metrics.set_meter_provider(MeterProvider(resource=resource))

# Structured logging (auto-collected by Alloy)
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ]
)
```

**Deployment annotations for auto-instrumentation**:
```yaml
# k8s/postgrest/base/deployment.yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "3000"
    prometheus.io/path: "/metrics"
spec:
  template:
    metadata:
      labels:
        app: postgrest
        app.kubernetes.io/part-of: dk-data-fe
```

### Step 6: Add Grafana Dashboards

Create dashboard in dk-alchemy GitOps:

```json
// dk-alchemy/grafana/dashboards/applications/dk-data-fe.json
{
  "title": "dk-data-fe Data Platform",
  "uid": "dk-data-fe",
  "panels": [
    {
      "title": "API Request Rate",
      "type": "timeseries",
      "datasource": "Mimir",
      "targets": [{"expr": "rate(http_requests_total{service=\"dk-data-fe\"}[5m])"}]
    },
    {
      "title": "Data Freshness",
      "type": "stat",
      "datasource": "PostgreSQL",
      "targets": [{"rawSql": "SELECT source_name, EXTRACT(EPOCH FROM NOW() - last_refresh)/3600 as hours_stale FROM meta.data_sources"}]
    },
    {
      "title": "Ingestion Job Status",
      "type": "table",
      "datasource": "PostgreSQL",
      "targets": [{"rawSql": "SELECT job_name, status, started_at, completed_at FROM meta.batch_job_runs ORDER BY started_at DESC LIMIT 20"}]
    }
  ]
}
```

Add alert rules:

```yaml
# dk-alchemy/grafana/alerts/dk-data-fe.yaml
groups:
  - name: dk-data-fe
    rules:
      - alert: DataStale
        expr: dk_data_fe_data_age_hours > 48
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Data source {{ $labels.source }} is stale"

      - alert: IngestionJobFailed
        expr: dk_data_fe_job_status{status="failed"} > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Ingestion job {{ $labels.job_name }} failed"
```

---

## 🔴 P0: Critical Security Issues

### 1. Credential Management (Issue #2) - ✅ USE DOPPLER

**Current State**: Hardcoded credentials in `docker-compose.yml` and `init_database.sql`

**Solution**: Leverage dk-alchemy's Doppler integration (already deployed)

**Action Items**:
- [ ] Add dk-data-fe secrets to Doppler `dk-infrastructure` project
- [ ] Create DopplerSecret CRD in dk-data-fe namespace
- [ ] Remove hardcoded passwords from SQL files (use env substitution)
- [ ] Create `.env.example` for local development (gitignored `.env`)
- [ ] Add pre-commit hook with gitleaks for secret scanning

**Local Development**:
```bash
# Use Doppler CLI for local secrets
doppler run --project dk-infrastructure --config dev -- docker-compose up
```

### 2. JWT Secret Configuration (Issue #3) - ✅ USE DOPPLER

**Current State**: Weak default JWT secret, no rotation mechanism

**Solution**: Store JWT secret in Doppler with strong generation

**Action Items**:
- [ ] Generate 256-bit JWT secret: `openssl rand -base64 32`
- [ ] Store in Doppler as `POSTGREST_JWT_SECRET`
- [ ] Configure PostgREST to use base64 decoding
- [ ] Document rotation procedure in runbook
- [ ] Add audience claim validation

```yaml
# PostgREST config via Doppler
PGRST_JWT_SECRET: "${POSTGREST_JWT_SECRET}"  # From Doppler
PGRST_JWT_SECRET_IS_BASE64: "true"
PGRST_JWT_AUD: "dk-data-fe-api"
```

### 3. API Access Control (Issue #4)

**Current State**: Overly permissive `web_anon` role

**Recommendations** (unchanged - this is application-level):
```sql
-- Principle of least privilege
GRANT SELECT ON api.catalog_public TO web_anon;
GRANT SELECT ON api.health TO web_anon;
REVOKE ALL ON api.targets FROM web_anon;
REVOKE ALL ON api.scoring FROM web_anon;

-- Create tiered access roles
CREATE ROLE internal_api;  -- Internal services
CREATE ROLE analyst;       -- Data analysts
CREATE ROLE ml_service;    -- AI/ML pipelines
```

**Rate Limiting via Traefik** (dk-alchemy):
```yaml
# k8s/postgrest/base/middleware.yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: dk-data-fe-ratelimit
spec:
  rateLimit:
    average: 100
    burst: 200
    period: 1m
```

**Action Items**:
- [ ] Audit all `GRANT` statements and reduce permissions
- [ ] Implement row-level security for sensitive tables
- [ ] Create service-specific API roles
- [ ] Configure Traefik rate limiting middleware
- [ ] Add API key authentication for external integrations

---

## 🟠 P1: Operations & Reliability

### 4. Observability Stack (Issue #11) - ✅ ALREADY AVAILABLE

**Status**: dk-alchemy provides complete observability stack

| Component | dk-alchemy Service | Endpoint |
|-----------|-------------------|----------|
| Metrics | Mimir | `mimir.infra.svc.cluster.local:9009` |
| Logs | Loki | `loki.infra.svc.cluster.local:3100` |
| Traces | Tempo | `tempo.infra.svc.cluster.local:4317` |
| Dashboards | Grafana | `grafana.infra.svc.cluster.local:3000` |
| Collector | Alloy | `alloy.infra.svc.cluster.local:4317` |

**Action Items** (instrument dk-data-fe apps):
- [ ] Add OpenTelemetry SDK to Python services
- [ ] Configure OTLP export to Alloy endpoint
- [ ] Add structlog for JSON logging (auto-collected)
- [ ] Create dk-data-fe dashboard in `dk-alchemy/grafana/dashboards/applications/`
- [ ] Add alert rules in `dk-alchemy/grafana/alerts/`
- [ ] Add Prometheus annotations to deployments

### 5. Database Backup & Recovery (Issue #13) - ✅ AVAILABLE VIA CNPG

**Status**: dk-alchemy's CNPG operator provides automated PostgreSQL backups

**Option A: Use Shared PostgreSQL** (simpler):
```yaml
# Request database in shared cluster
# Backups handled automatically by CNPG → MinIO
```

**Option B: Dedicated CNPG Cluster** (recommended for isolation):
```yaml
# k8s/postgres/base/cluster.yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: dk-data-fe-postgres
  namespace: dk-data-fe-prod
spec:
  instances: 2  # HA with automatic failover

  storage:
    storageClass: local-path-fast  # NVMe storage
    size: 50Gi

  backup:
    barmanObjectStore:
      destinationPath: s3://dk-data-fe-backups/postgres/
      endpointURL: http://minio.infra.svc.cluster.local:9000
      s3Credentials:
        accessKeyId:
          name: minio-credentials
          key: access-key
        secretAccessKey:
          name: minio-credentials
          key: secret-key
    retentionPolicy: "30d"

  bootstrap:
    initdb:
      database: dk_data
      owner: app_user
```

**Action Items**:
- [ ] Decide: shared vs dedicated PostgreSQL cluster
- [ ] If dedicated: create CNPG Cluster CRD
- [ ] Configure backup retention policy (30 days recommended)
- [ ] Document and test recovery procedures
- [ ] Set up backup monitoring alerts

### 6. Kubernetes Resource Management (Issue #12)

**Status**: Need to add resource specs to dk-data-fe deployments

**Use dk-alchemy components**:
```yaml
# k8s/postgrest/overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

components:
  # Import shared HPA and PDB from dk-alchemy
  - ../../../../../dk-alchemy/k8s/components/hpa-production
  - ../../../../../dk-alchemy/k8s/components/pdb-standard

patches:
  - path: resources-patch.yaml
```

```yaml
# k8s/postgrest/overlays/prod/resources-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgrest
spec:
  template:
    spec:
      containers:
      - name: postgrest
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

**Resource Guidelines**:
| Service | Memory Request | Memory Limit | CPU Request | CPU Limit |
|---------|---------------|--------------|-------------|-----------|
| PostgREST | 256Mi | 512Mi | 100m | 500m |
| Job Trigger | 128Mi | 256Mi | 50m | 200m |
| Ingestion Jobs | 512Mi | 2Gi | 200m | 1000m |
| SQLMesh Jobs | 1Gi | 4Gi | 500m | 2000m |

**Action Items**:
- [ ] Add resource requests/limits to all deployments
- [ ] Use dk-alchemy HPA component for PostgREST
- [ ] Use dk-alchemy PDB component for high availability
- [ ] Add namespace resource quotas

### 7. External API Resilience (Issue #5)

**Status**: Application-level changes required

**Leverage Redis for caching** (available in dk-alchemy):
```python
import redis
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

# Connect to shared Redis
redis_client = redis.Redis(
    host="redis-master.infra.svc.cluster.local",
    port=6379,
    decode_responses=True
)

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=60, jitter=5)
)
def fetch_with_cache(url: str, ttl: int = 3600) -> dict:
    cache_key = f"api_cache:{hashlib.md5(url.encode()).hexdigest()}"

    # Check cache first
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Fetch and cache
    response = session.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    redis_client.setex(cache_key, ttl, json.dumps(data))
    return data
```

**Action Items**:
- [ ] Replace urllib3 Retry with tenacity
- [ ] Add circuit breaker pattern (pybreaker)
- [ ] Implement Redis caching layer for external APIs
- [ ] Add fallback data sources (CSV snapshots in MinIO)
- [ ] Create monitoring for external API health

### 8. Job Monitoring & Alerting (Issue #6) - ✅ USE GRAFANA ALERTS

**Status**: Leverage dk-alchemy's Grafana alerting

**Add dk-data-fe specific alerts**:
```yaml
# dk-alchemy/grafana/alerts/dk-data-fe.yaml
groups:
  - name: dk-data-fe-jobs
    rules:
      - alert: IngestionJobFailed
        expr: |
          kube_job_status_failed{namespace="dk-data-fe-prod"} > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Ingestion job {{ $labels.job_name }} failed"

      - alert: DataFreshnessSLA
        expr: |
          (time() - dk_data_fe_last_ingestion_timestamp{}) / 3600 > 48
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Data source {{ $labels.source }} exceeds 48h freshness SLA"

      - alert: CronJobMissedSchedule
        expr: |
          time() - kube_cronjob_status_last_schedule_time{namespace="dk-data-fe-prod"} > 86400
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "CronJob {{ $labels.cronjob }} missed scheduled execution"
```

**Expose custom metrics**:
```python
# src/dk_data/metrics.py
from prometheus_client import Counter, Gauge, Histogram

# Job metrics
job_runs_total = Counter(
    'dk_data_fe_job_runs_total',
    'Total job runs',
    ['job_name', 'status']
)

job_duration_seconds = Histogram(
    'dk_data_fe_job_duration_seconds',
    'Job execution duration',
    ['job_name']
)

# Data freshness metrics
data_freshness_hours = Gauge(
    'dk_data_fe_data_freshness_hours',
    'Hours since last data refresh',
    ['source']
)

rows_ingested_total = Counter(
    'dk_data_fe_rows_ingested_total',
    'Total rows ingested',
    ['source', 'table']
)
```

**Action Items**:
- [ ] Add Prometheus metrics to ingestion jobs
- [ ] Create data freshness gauge metrics
- [ ] Add alert rules to dk-alchemy/grafana/alerts/
- [ ] Configure Slack/PagerDuty integration (if not already)
- [ ] Create job dependency tracking view

---

## 🟡 P2: Compliance & Governance

### 9. Audit Trail (Issue #17)

**Recommendations** (unchanged - database-level):
```sql
-- Enable pgAudit extension
CREATE EXTENSION IF NOT EXISTS pgaudit;

-- Configure audit logging
ALTER SYSTEM SET pgaudit.log = 'write, ddl';
ALTER SYSTEM SET pgaudit.log_catalog = off;
ALTER SYSTEM SET pgaudit.log_level = 'log';

-- Logs automatically collected by Loki via dk-alchemy's Alloy
```

**Action Items**:
- [ ] Enable pgAudit extension in CNPG cluster config
- [ ] Create history tables for sensitive data
- [ ] Implement CDC triggers for targeting tables
- [ ] Logs auto-shipped to Loki (retention configured in dk-alchemy)
- [ ] Create Grafana dashboard for audit queries

### 10. PII/PHI Data Handling (Issue #18)

**Recommendations** (unchanged - application-level):
```sql
-- Data classification schema
CREATE TABLE meta.data_classification (
    table_schema TEXT,
    table_name TEXT,
    column_name TEXT,
    classification TEXT CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'PHI')),
    pii_type TEXT,
    masking_rule TEXT,
    retention_days INT
);

-- Dynamic data masking
CREATE VIEW api.champions_masked AS
SELECT
    id,
    hospital_id,
    CASE WHEN current_user IN ('analyst', 'web_anon')
         THEN regexp_replace(email, '(.{2}).*@', '\1***@')
         ELSE email
    END as email,
    role
FROM targeting.champions;
```

**Action Items**:
- [ ] Inventory all data fields and classify sensitivity
- [ ] Implement encryption for PHI columns (pgcrypto)
- [ ] Create masked views for analyst access
- [ ] Document data flow diagrams showing PHI paths
- [ ] Add data processing agreements (DPA) documentation

### 11. Data Retention Policy (Issue #19)

**Recommendations** (unchanged - application-level):
```sql
-- Retention policy table
CREATE TABLE meta.retention_policies (
    schema_name TEXT,
    table_name TEXT,
    retention_days INT NOT NULL,
    archive_strategy TEXT CHECK (archive_strategy IN ('DELETE', 'ARCHIVE', 'ANONYMIZE')),
    legal_hold BOOLEAN DEFAULT FALSE
);

-- Archive to MinIO before deletion
CREATE OR REPLACE FUNCTION archive_and_delete()
RETURNS void AS $$
BEGIN
    -- Export to MinIO via pg_dump or COPY TO
    -- Then delete from source table
END;
$$ LANGUAGE plpgsql;
```

**Action Items**:
- [ ] Define retention periods by data classification
- [ ] Create automated retention CronJob
- [ ] Archive to MinIO before deletion
- [ ] Implement legal hold capability
- [ ] Document data lifecycle

### 12. Database Migration Strategy (Issue #9)

**Recommendations** (unchanged):
```python
# Use Alembic for migrations
# migrations/
# ├── versions/
# │   ├── 001_initial_schema.sql
# │   └── ...
# ├── alembic.ini
# └── env.py
```

**Action Items**:
- [ ] Set up Alembic for migrations
- [ ] Convert existing SQL to versioned migrations
- [ ] Add migration CI checks
- [ ] Integrate with ArgoCD sync hooks

---

## 🟢 P3: Architecture & Quality

### 13. Multi-Tenancy & Generalization (Issue #8)

**Recommendations** (unchanged):
```yaml
# config/project.yaml
project:
  name: "${PROJECT_NAME:-dk-data}"
  database: "${DATABASE_NAME:-data_platform}"
  namespace: "${K8S_NAMESPACE:-dk-data-fe}"

data_domains:
  - name: tavr
    enabled: true
    schemas: [raw_tavr, staging_tavr, mart_tavr]
```

**Action Items**:
- [ ] Create configuration layer for project naming
- [ ] Implement domain-based schema partitioning
- [ ] Document multi-tenancy patterns
- [ ] Create template for new therapeutic areas

### 14. Test Coverage (Issue #15)

**Action Items** (unchanged):
- [ ] Add pytest-cov to measure coverage
- [ ] Write unit tests for validators and utilities
- [ ] Add integration tests with pytest-postgresql
- [ ] Implement Great Expectations for data quality
- [ ] Add CI gates for coverage thresholds (80% target)

### 15. Error Handling (Issue #14)

**Action Items** (unchanged):
- [ ] Define error taxonomy and severity levels
- [ ] Implement structured IngestionResult returns
- [ ] Add error aggregation and reporting
- [ ] Create runbooks for common error scenarios
- [ ] Add error metrics to observability (Mimir)

### 16. Dependency Management (Issue #20)

**Action Items** (unchanged):
- [ ] Add upper version bounds to all dependencies
- [ ] Commit uv.lock file
- [ ] Split dev/prod dependencies
- [ ] Configure Dependabot for automated updates
- [ ] Add security scanning (safety, pip-audit)

### 17. Version Alignment (Issue #21)

**Follow dk-alchemy patterns**:
- PostgREST images managed via ArgoCD Image Updater
- Versions pinned in kustomization.yaml

**Action Items**:
- [ ] Align PostgREST version across docker-compose and k8s
- [ ] Let ArgoCD Image Updater manage version updates
- [ ] Document version upgrade procedures

---

## AI/ML Platform Integration

### Integration with Behavior Labs AI

dk-data-fe should integrate with the existing Behavior Labs platform (also deployed via dk-alchemy):

```
┌─────────────────────────────────────────────────────────────────┐
│                     dk-alchemy Kubernetes Cluster               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐    ┌──────────────────────┐          │
│  │  behaviorlabs-prod   │    │   dk-data-fe-prod    │          │
│  │  ┌────────────────┐  │    │  ┌────────────────┐  │          │
│  │  │   ML Models    │  │◄───│  │   PostgREST    │  │          │
│  │  │   LLM Agents   │  │    │  │   API Layer    │  │          │
│  │  └────────────────┘  │    │  └───────┬────────┘  │          │
│  └──────────────────────┘    │          │           │          │
│                              │  ┌───────▼────────┐  │          │
│                              │  │   PostgreSQL   │  │          │
│                              │  │  (CNPG/shared) │  │          │
│                              │  └────────────────┘  │          │
│                              └──────────────────────┘          │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │                    infra namespace                         ││
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ││
│  │  │ Mimir  │ │  Loki  │ │ Tempo  │ │Grafana │ │ Doppler  │ ││
│  │  │metrics │ │  logs  │ │ traces │ │dashbrd │ │ secrets  │ ││
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘ ││
│  └────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Feature Store for ML

```sql
-- Expose features via PostgREST for ML consumption
CREATE MATERIALIZED VIEW ml.hospital_features AS
SELECT
    h.hospital_id,
    h.bed_count,
    h.teaching_status,
    t.volume_2023,
    t.yoy_growth,
    f.operating_margin,
    s.target_score
FROM mart.dim_hospital h
JOIN mart.fact_tavr_program t USING (hospital_id)
JOIN mart.fact_financial_metrics f USING (hospital_id)
JOIN scoring.target_scores s USING (hospital_id);

-- API endpoint: GET /hospital_features
GRANT SELECT ON ml.hospital_features TO ml_service;
```

### LiteLLM Integration

dk-alchemy provides LiteLLM proxy for unified LLM access:
```python
# Use LiteLLM for Claude SDK enrichment
import litellm

litellm.api_base = "http://litellm.infra.svc.cluster.local:4000"

response = litellm.completion(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Enrich hospital data..."}]
)
```

---

## Revised Implementation Roadmap

### Phase 1: dk-alchemy Integration (Week 1)
1. Create bootstrap application in dk-alchemy
2. Restructure dk-data-fe for GitOps patterns
3. Add secrets to Doppler
4. Configure namespace and RBAC

### Phase 2: Security & Observability (Week 2)
1. Remove hardcoded credentials
2. Configure JWT via Doppler
3. Instrument apps for OTLP
4. Create Grafana dashboards and alerts

### Phase 3: Database & Storage (Week 3)
1. Deploy CNPG cluster (or use shared)
2. Configure automated backups to MinIO
3. Set up Redis caching for external APIs
4. Implement API access control

### Phase 4: Compliance & Quality (Week 4-5)
1. Enable pgAudit for audit trail
2. Implement data retention policies
3. Add test coverage
4. Set up database migrations

### Phase 5: ML Platform Integration (Week 6)
1. Create feature store materialized views
2. Configure ML service role
3. Integrate with Behavior Labs platform
4. Add prediction logging

---

## 🧹 Codebase Cleanup & Technical Debt

### Overview

A thorough analysis of the dk-data-fe codebase identified significant duplication, inconsistent organization, and committed artifacts that should be cleaned up before production deployment.

### Cleanup Priority Matrix

| Priority | Category | Items | Impact |
|----------|----------|-------|--------|
| 🔴 **Critical** | Duplicate Code | 18 files | Maintenance risk, confusion |
| 🔴 **Critical** | Committed Data | 74+ MB | Repository bloat, security |
| 🟠 **High** | Config Sprawl | 6 files | Inconsistent deployments |
| 🟠 **High** | Documentation | 8+ files | Confusion, drift |
| 🟡 **Medium** | Dead Code | ~20 instances | Code quality |
| 🟢 **Low** | Naming | Various | Developer experience |

---

### 🔴 Critical: Duplicate Files

#### 1. Duplicate Python Scripts (14 files)

Scripts exist in **BOTH** `/scripts/` AND `/src/dk_data/scripts/`:

| Script | Location 1 | Location 2 | Status |
|--------|-----------|------------|--------|
| `catalog_refresh.py` | `/scripts/data/` | `/src/dk_data/scripts/` | Identical |
| `check_freshness.py` | `/scripts/data/` | `/src/dk_data/scripts/` | Identical |
| `load_targeting_data.py` | `/scripts/data/` | `/src/dk_data/scripts/` | Identical |
| `purge_history.py` | `/scripts/data/` | `/src/dk_data/scripts/` | Identical |
| `run_enrichment.py` | `/scripts/data/` | `/src/dk_data/scripts/` | Identical |
| `validate_api.py` | `/scripts/ops/` | `/src/dk_data/scripts/` | Identical |
| `validate_performance.py` | `/scripts/ops/` | `/src/dk_data/scripts/` | Identical |
| `metabase_client.py` | `/scripts/utils/` | `/src/dk_data/scripts/` | Identical |
| `provision_metabase.py` | `/scripts/utils/` | `/src/dk_data/scripts/` | Identical |
| `setup_logging.py` | `/scripts/utils/` | `/src/dk_data/scripts/` | Identical |

**Action Items**:
- [ ] Choose canonical location: `/src/dk_data/scripts/` (follows package structure)
- [ ] Remove `/scripts/` directory entirely
- [ ] Update docker-compose.yml volume mounts (remove legacy mount at line 110)
- [ ] Update Makefile references

#### 2. Duplicate Shell Scripts (4 files)

| Script | Location 1 | Location 2 |
|--------|-----------|------------|
| `install_cron.sh` | `/scripts/ops/` | `/src/dk_data/scripts/` |
| `start_api.sh` | `/scripts/ops/` | `/src/dk_data/scripts/` |
| `refresh_data.sh` | `/scripts/data/` | `/src/dk_data/scripts/` |
| `run_sqlmesh.sh` | `/scripts/data/` | `/src/dk_data/scripts/` |

**Action Items**:
- [ ] Consolidate to `/src/dk_data/scripts/`
- [ ] Remove duplicates from `/scripts/`

#### 3. Duplicate SQL Table Definitions

**Critical Issue**: Two different versions of targeting tables exist:

| File | Lines | Tables | Status |
|------|-------|--------|--------|
| `/src/dk_data/database/targeting_tables.sql` | 126 | 5 tables | Simplified, outdated |
| `/src/dk_data/sql/targeting_tables.sql` | 348 | 6 tables | Complete, with constraints |

**Differences**:
- `/sql/` version has `targeting.financial_details` table (missing in `/database/`)
- `/sql/` version has proper CHECK constraints and audit columns
- `/database/` version is an earlier, simplified version

**Action Items**:
- [ ] Keep `/src/dk_data/sql/targeting_tables.sql` as canonical
- [ ] Delete `/src/dk_data/database/targeting_tables.sql`
- [ ] Verify no references to deleted file remain

---

### 🔴 Critical: Committed Artifacts

#### 1. Data Files (74+ MB)

**Location**: `/data/raw/`

| File | Size |
|------|------|
| `cms_inpatient_full_fy2021_20260115.csv` | 38 MB |
| `cms_inpatient_full_fy2022_20260115.csv` | 36 MB |
| `cms_inpatient_tavr_fy2021_20260115.csv` | 322 KB |
| `cms_inpatient_tavr_fy2022_20260115.csv` | 329 KB |

**Issue**: These are in `.gitignore` but were committed before the ignore rule was added.

**Action Items**:
- [ ] Remove data files from git history: `git filter-branch` or `git-filter-repo`
- [ ] Verify `.gitignore` covers `/data/` directory
- [ ] Add data files to MinIO for persistence (not git)

#### 2. Log Files (1.5 MB)

**Location**: `/logs/`

| Pattern | Count |
|---------|-------|
| `sqlmesh_2026_01_14_*.log` | ~10 files |
| `sqlmesh_2026_01_15_*.log` | ~10 files |

**Action Items**:
- [ ] Remove log files from git: `git rm -r --cached logs/`
- [ ] Verify `.gitignore` line 47 (`logs/`) is effective
- [ ] Configure log shipping to Loki instead of local files

#### 3. Python Bytecode

**Issue**: `__pycache__/` directories may be in git history.

**Action Items**:
- [ ] Run: `find . -type d -name __pycache__ -exec rm -rf {} +`
- [ ] Run: `git rm -r --cached '**/__pycache__'`
- [ ] Verify `.gitignore` covers `__pycache__/` and `*.pyc`

---

### 🟠 High: Configuration Sprawl

#### 1. Dual Makefile Structure

| File | Lines | Purpose |
|------|-------|---------|
| `/Makefile` | 402 | Root orchestration |
| `/src/dk_data/Makefile` | 444 | Detailed tasks |

**Problem**: Overlapping targets, unclear which is primary.

**Action Items**:
- [ ] Consolidate to single `/Makefile` at root
- [ ] Move detailed targets to root Makefile with proper grouping
- [ ] Delete `/src/dk_data/Makefile`
- [ ] Update documentation to reference single Makefile

#### 2. Dependency Specification Mismatch

| File | Dependencies | Missing |
|------|-------------|---------|
| `/pyproject.toml` | 16 packages | `fastapi`, `uvicorn`, `kubernetes` |
| `/src/dk_data/requirements.txt` | 15+ packages | Complete |

**Problem**: Installing via `pip install .` won't include FastAPI dependencies needed for job-trigger.

**Action Items**:
- [ ] Sync `pyproject.toml` dependencies with `requirements.txt`
- [ ] Add missing: `fastapi>=0.109.0`, `uvicorn>=0.27.0`, `kubernetes>=29.0.0`
- [ ] Consider making `requirements.txt` generated from `pyproject.toml`

#### 3. Docker Compose Files

| File | Lines | Purpose |
|------|-------|---------|
| `/src/dk_data/docker-compose.yml` | 168 | Main compose |
| `/src/dk_data/docker-compose.prod.yml` | 69 | Production overrides |

**Action Items**:
- [ ] Move to root: `/docker-compose.yml` and `/docker-compose.prod.yml`
- [ ] Or rename to `/docker/compose.yml` for clarity
- [ ] Update documentation paths

---

### 🟠 High: Documentation Redundancy

#### Overlapping Documentation

| File | Lines | Topic |
|------|-------|-------|
| `ARCHITECTURE.md` | 1304 | System design |
| `README.md` | 328 | Quick start |
| `RECOMMENDATIONS.md` | 1011 | Platform recommendations |
| `docs/api-examples.md` | 353 | API usage |
| `docs/DATA_PIPELINE_STATUS.md` | 277 | Pipeline status |
| `specs/001.../spec.md` | ~300 | Feature specification |
| `specs/001.../quickstart.md` | ~100 | Quick start (duplicates README) |
| `CLAUDE.md` | 29 | Auto-generated |

**Problem**: Architecture described in 5+ places; API examples in 3+ places.

**Action Items**:
- [ ] Keep `README.md` as entry point (quick start only)
- [ ] Keep `ARCHITECTURE.md` as detailed reference
- [ ] Keep `RECOMMENDATIONS.md` as operational guide
- [ ] Move `docs/api-examples.md` content to `ARCHITECTURE.md`
- [ ] Delete `specs/001.../quickstart.md` (duplicates README)
- [ ] Archive `DATA_PIPELINE_STATUS.md` or merge into ARCHITECTURE.md
- [ ] Add "Documentation Map" to README showing what's where

---

### 🟡 Medium: Dead Code & Unused Imports

#### Unused `json` Import

Files with `import json` but no usage (use `psycopg2.extras.Json` instead):

| File | Line |
|------|------|
| `/scripts/data/catalog_refresh.py` | 15 |
| `/scripts/ops/validate_api.py` | ~5 |
| `/scripts/ops/validate_performance.py` | ~5 |

**Action Items**:
- [ ] Run `ruff check --select F401` to find all unused imports
- [ ] Remove unused imports
- [ ] Add `ruff` to CI to prevent future issues

#### Unnecessary `sys.path` Manipulation

Multiple files use this pattern unnecessarily:
```python
sys.path.insert(0, str(__file__).rsplit('/scripts', 1)[0])
```

**Files affected**:
- `/src/dk_data/ingestion/fetch_data.py` (lines 17-18)
- Various scripts in `/scripts/`

**Action Items**:
- [ ] Remove `sys.path` manipulation from package modules
- [ ] Rely on proper package installation via `pyproject.toml`

---

### 🟡 Medium: GitOps Structure Issues

#### Current Structure vs dk-alchemy Pattern

**Current** (missing items marked with ❌):

```
.gitops/
├── base/
│   ├── catalog/
│   ├── ingestion/
│   └── postgrest/
├── overlays/
│   ├── dev/
│   ├── staging/
│   └── prod/
└── argocd/
    └── application.yaml
```

**Missing for dk-alchemy integration**:
- ❌ `namespace.yaml` - Namespace definition
- ❌ `serviceaccount.yaml` - Service accounts
- ❌ `networkpolicy.yaml` - Network isolation
- ❌ `ingress.yaml` or `ingressroute.yaml` - External access
- ❌ `doppler-secret.yaml` - Doppler integration
- ❌ Proper kustomization.yaml files following dk-alchemy patterns

**Action Items**:
- [ ] Restructure to match dk-alchemy external app pattern
- [ ] Add missing resources (namespace, service account, network policy)
- [ ] Create proper `kustomization.yaml` with component references
- [ ] Add DopplerSecret CRD for secrets management

---

### 🟢 Low: Naming Inconsistencies

#### Fetcher Method Naming

Inconsistent method names across fetcher classes:

| Fetcher | Methods |
|---------|---------|
| `CMSInpatientFetcher` | `get_download_url()`, `get_api_endpoints()` |
| `CMSHospitalInfoFetcher` | `get_api_endpoints()` |
| `CMSCostReportsFetcher` | `get_api_endpoints()` |
| `HRSAFetcher` | Different pattern |

**Action Items**:
- [ ] Standardize fetcher interface methods
- [ ] Document expected methods in `BaseFetcher` docstring
- [ ] Consider adding abstract methods for required interface

#### SQL Comment Style Inconsistency

| File | Style |
|------|-------|
| `/database/targeting_tables.sql` | Simple: `COMMENT ON TABLE...` |
| `/sql/targeting_tables.sql` | Detailed: `-- T002: Purpose...` |

**Action Items**:
- [ ] After consolidating SQL files, standardize comment style
- [ ] Use task-based comments (`-- T00X:`) for traceability

---

### Cleanup Implementation Plan

#### Week 1: Critical Cleanup
```bash
# 1. Remove duplicate scripts
rm -rf scripts/

# 2. Remove duplicate SQL
rm src/dk_data/database/targeting_tables.sql

# 3. Remove committed artifacts from git
git rm -r --cached data/ logs/
git commit -m "Remove committed data and log files"

# 4. Clean git history (optional, requires force push)
git filter-repo --invert-paths --path data/ --path logs/
```

#### Week 2: Configuration Consolidation
```bash
# 1. Consolidate Makefile
cat src/dk_data/Makefile >> Makefile  # Merge unique targets
rm src/dk_data/Makefile

# 2. Sync dependencies
# Edit pyproject.toml to add missing deps

# 3. Move docker-compose to root
mv src/dk_data/docker-compose*.yml ./
```

#### Week 3: Documentation & GitOps
```bash
# 1. Consolidate documentation
# Manual: merge api-examples.md into ARCHITECTURE.md
rm specs/001-data-layer-postgrest-gitops/quickstart.md

# 2. Restructure .gitops/
# Follow dk-alchemy patterns
```

---

### Cleanup Checklist

#### Critical (Do First)
- [ ] Remove `/scripts/` directory (keep `/src/dk_data/scripts/`)
- [ ] Remove `/src/dk_data/database/targeting_tables.sql`
- [ ] Remove committed data files from git
- [ ] Remove committed log files from git
- [ ] Sync `pyproject.toml` with `requirements.txt`

#### High Priority
- [ ] Consolidate to single Makefile
- [ ] Consolidate documentation
- [ ] Fix docker-compose location
- [ ] Update .gitignore and verify effectiveness

#### Medium Priority
- [ ] Remove unused imports (run `ruff`)
- [ ] Remove unnecessary `sys.path` manipulation
- [ ] Restructure `.gitops/` for dk-alchemy
- [ ] Add missing GitOps resources

#### Low Priority
- [ ] Standardize fetcher method names
- [ ] Standardize SQL comment style
- [ ] Add documentation map to README

---

## Summary: What's New vs What's Available

| Capability | Build New | Use dk-alchemy | Notes |
|------------|-----------|----------------|-------|
| Observability | ❌ | ✅ | Mimir/Loki/Tempo/Grafana |
| Secrets Management | ❌ | ✅ | Doppler Operator |
| PostgreSQL HA | ❌ | ✅ | CNPG Operator |
| Backups | ❌ | ✅ | CNPG → MinIO |
| TLS Certificates | ❌ | ✅ | cert-manager |
| Ingress | ❌ | ✅ | Traefik |
| GitOps | ❌ | ✅ | ArgoCD |
| Caching | ❌ | ✅ | Redis |
| Object Storage | ❌ | ✅ | MinIO |
| LLM Proxy | ❌ | ✅ | LiteLLM |
| API Security | ✅ | - | PostgREST RBAC |
| Data Validation | ✅ | - | Application code |
| Test Coverage | ✅ | - | Application code |
| Audit Trail | ✅ | Partial | pgAudit + Loki |
| Data Retention | ✅ | - | Application code |

---

## References

- [dk-alchemy Documentation](https://github.com/data-kinetic/dk-alchemy/tree/main/docs)
- [CNPG Documentation](https://cloudnative-pg.io/documentation/)
- [Doppler Documentation](https://docs.doppler.com/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [ArgoCD ApplicationSets](https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/)

---

*Document generated: 2026-01-20*
*Updated with dk-alchemy integration recommendations*
*Next review: After Phase 1 completion*

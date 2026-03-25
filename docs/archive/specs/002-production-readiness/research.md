# Research: Production Readiness for dk-data-fe

**Feature**: 002-production-readiness
**Date**: 2026-01-20
**Phase**: 0 (Technical Analysis)

## Executive Summary

This research document analyzes the technical requirements and implementation approaches for making dk-data-fe production-ready. The analysis covers four primary areas: security hardening, codebase cleanup, observability integration, and GitOps restructuring.

**Key Finding**: The dk-alchemy shared infrastructure provides most required production capabilities. This reduces implementation effort from building infrastructure to integration work.

## 1. Security Analysis

### 1.1 Current State

**Hardcoded Credentials Found**:
| Location | Type | Risk |
|----------|------|------|
| `.gitops/base/postgrest/secret.yaml:18` | Database URI with password | Critical |
| `.gitops/base/postgrest/secret.yaml:23` | JWT secret placeholder | Critical |
| `src/dk_data/docker-compose.yml:34` | POSTGRES_PASSWORD default | High |
| `src/dk_data/docker-compose.yml:61` | POSTGREST_PASSWORD in URI | High |

**JWT Configuration Issues**:
- Current: Placeholder secret "REPLACE_WITH_SECURE_SECRET_IN_PRODUCTION"
- `web_anon` role has full read access to all API endpoints
- No rate limiting configured on PostgREST

### 1.2 Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Doppler (dk-alchemy)                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ POSTGRES_PASS   │  │ JWT_SECRET      │  │ ANTHROPIC_API_KEY   │ │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘ │
└───────────┼─────────────────────┼─────────────────────┼────────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌───────────────────────────────────────────────────────────────────┐
│                    DopplerSecret CRD (K8s)                        │
│        Syncs secrets to Kubernetes Secret objects                 │
└───────────────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│    PostgREST      │  │   Job-Trigger     │  │   CronJobs        │
│   (reads JWT)     │  │  (reads DB pass)  │  │  (reads secrets)  │
└───────────────────┘  └───────────────────┘  └───────────────────┘
```

### 1.3 Doppler Integration Pattern

Following dk-alchemy patterns from `/Users/nicholas/Code/dk-alchemy/k8s/infrastructure/doppler-operator/`:

```yaml
# DopplerSecret for dk-data-fe
apiVersion: secrets.doppler.com/v1alpha1
kind: DopplerSecret
metadata:
  name: dk-data-fe-secrets
  namespace: dk-data-fe-prod
spec:
  tokenSecret:
    name: doppler-token-secret
  config: prod
  project: dk-infrastructure
  managedSecret:
    name: dk-data-fe-secrets
    type: Opaque
  resyncSeconds: 300  # Re-sync every 5 minutes for rotation
```

### 1.4 JWT Hardening Approach

**Current PostgREST roles**:
- `web_anon`: Anonymous access (currently too permissive)
- `authenticator`: Connection role
- `analyst`: Extended read access (via JWT)
- `api_user`: Full read access (via JWT)

**Target role permissions**:
```sql
-- Restrict web_anon to health endpoints only
REVOKE ALL ON SCHEMA api FROM web_anon;
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON api.health TO web_anon;
GRANT SELECT ON api.data_catalog TO web_anon;  -- Public catalog only

-- analyst role: Read access to analysis tables
GRANT SELECT ON api.targets TO analyst;
GRANT SELECT ON api.scoring TO analyst;
GRANT SELECT ON api.data_sources TO analyst;

-- api_user role: Full read access
GRANT SELECT ON ALL TABLES IN SCHEMA api TO api_user;
```

**Rate limiting via Traefik middleware**:
```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: rate-limit
spec:
  rateLimit:
    average: 100
    burst: 50
    period: 1m
    sourceCriterion:
      ipStrategy:
        depth: 1
```

## 2. Codebase Cleanup Analysis

### 2.1 Duplicate Files Inventory

**Python Scripts (14 duplicates)**:
| File | `/scripts/` | `/src/dk_data/scripts/` | Action |
|------|-------------|-------------------------|--------|
| `catalog_refresh.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `check_freshness.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `load_targeting_data.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `metabase_client.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `provision_metabase.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `purge_history.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `run_enrichment.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `setup_logging.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `validate_api.py` | ✓ | ✓ | Keep src/, remove scripts/ |
| `validate_performance.py` | ✓ | ✓ | Keep src/, remove scripts/ |

**Shell Scripts (4 duplicates)**:
| File | Location 1 | Location 2 | Action |
|------|------------|------------|--------|
| `start_services.sh` | `/scripts/` | `/src/dk_data/scripts/` | Keep src/ |
| `run_tests.sh` | `/scripts/` | `/src/dk_data/scripts/` | Keep src/ |
| `init_db.sh` | `/scripts/` | `/src/dk_data/scripts/` | Keep src/ |
| `backup.sh` | `/scripts/` | `/src/dk_data/scripts/` | Keep src/ |

**SQL Files**:
| File | Locations | Action |
|------|-----------|--------|
| `targeting_tables.sql` | `/sql/`, `/src/dk_data/sql/` | Keep src/dk_data/sql/ |
| `init_database.sql` | `/sql/`, `/src/dk_data/sql/` | Keep src/dk_data/sql/ |

### 2.2 Repository Size Analysis

**Current git objects**:
```
Total repository size: ~84 MB
├── data/raw/*.csv      74 MB (committed data files)
├── logs/sqlmesh/        3 MB (log files)
├── .git/objects        80 MB (accumulated history)
└── source code          4 MB
```

**Target after cleanup**: < 10 MB

### 2.3 Git History Rewrite Strategy

**Tool**: `git-filter-repo` (preferred over BFG or filter-branch)

```bash
# Step 1: Create backup branch
git branch backup-before-cleanup

# Step 2: Remove large files from history
git filter-repo --path data/ --invert-paths
git filter-repo --path logs/ --invert-paths

# Step 3: Remove secrets from history
git filter-repo --blob-callback '
    if b"postgres:" in blob.data or b"changeme" in blob.data:
        blob.data = blob.data.replace(b"changeme", b"REDACTED")
'

# Step 4: Force push (requires coordination)
git push --force --all
```

**Migration Path for Data Files**:
1. Upload current data to MinIO bucket `dk-data-fe/raw/`
2. Add `.gitignore` entries for `data/` and `logs/`
3. Update docker-compose to mount MinIO or local `./data` for development
4. Document data retrieval process in README

## 3. Observability Integration

### 3.1 dk-alchemy Observability Stack

Available services from dk-alchemy:
| Service | Endpoint | Protocol | Purpose |
|---------|----------|----------|---------|
| Alloy | `alloy.monitoring:4317` | OTLP/gRPC | Telemetry collector |
| Mimir | `mimir.monitoring:9009` | Prometheus | Metrics storage |
| Loki | `loki.monitoring:3100` | HTTP | Log aggregation |
| Tempo | `tempo.monitoring:4317` | OTLP | Trace storage |
| Grafana | `grafana.monitoring:3000` | HTTP | Dashboards |

### 3.2 Python Instrumentation

**Required packages** (add to pyproject.toml):
```toml
[project.dependencies]
# ... existing deps ...
opentelemetry-api = ">=1.20.0"
opentelemetry-sdk = ">=1.20.0"
opentelemetry-exporter-otlp = ">=1.20.0"
opentelemetry-instrumentation-fastapi = ">=0.41b0"
opentelemetry-instrumentation-psycopg2 = ">=0.41b0"
opentelemetry-instrumentation-requests = ">=0.41b0"
structlog = ">=24.0.0"
prometheus-client = ">=0.19.0"
```

**Instrumentation pattern**:
```python
# src/dk_data/observability/__init__.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

def setup_telemetry(service_name: str):
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint="alloy.monitoring:4317", insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
```

### 3.3 Grafana Dashboard Requirements

**Data Freshness Dashboard**:
- Panel: Data source last refresh timestamps
- Panel: Staleness alerts (>48 hours threshold)
- Panel: Row count trends by source

**API Health Dashboard**:
- Panel: Request rate by endpoint
- Panel: Error rate by status code
- Panel: Latency percentiles (p50, p95, p99)
- Panel: Active connections

**Job Monitoring Dashboard**:
- Panel: Job execution timeline
- Panel: Success/failure counts
- Panel: Duration by job type
- Panel: Records processed per run

### 3.4 Alert Rules

```yaml
# Prometheus alert rules for dk-data-fe
groups:
  - name: dk-data-fe
    rules:
      - alert: DataSourceStale
        expr: time() - dk_data_source_last_refresh_timestamp > 172800
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Data source {{ $labels.source }} is stale"

      - alert: APIHighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical

      - alert: JobFailure
        expr: increase(batch_job_failures_total[1h]) > 0
        for: 0m
        labels:
          severity: warning
```

## 4. GitOps Restructuring

### 4.1 Current vs Target Structure

**Current** (needs migration):
```
.gitops/
├── argocd/application.yaml     # Single app definition
├── base/                       # Kustomize base
│   ├── kustomization.yaml
│   ├── postgrest/
│   ├── ingestion/
│   └── catalog/
└── overlays/
    ├── dev/
    ├── staging/
    └── prod/
```

**Target** (dk-alchemy pattern):
```
.gitops/
├── prod/apps/                  # ArgoCD Applications for prod
│   ├── kustomization.yaml
│   ├── postgrest-app.yaml
│   ├── job-trigger-app.yaml
│   └── cronjobs-app.yaml
└── staging/apps/               # ArgoCD Applications for staging
    └── ...

k8s/                            # Kubernetes manifests (new location)
├── postgrest/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── service-monitor.yaml
│   │   └── configmap.yaml
│   └── overlays/
│       ├── prod/
│       │   ├── kustomization.yaml
│       │   ├── doppler-secret.yaml
│       │   └── ingress-route.yaml
│       └── staging/
│           └── kustomization.yaml
├── job-trigger/
│   └── ... (same pattern)
└── cronjobs/
    └── ... (same pattern)
```

### 4.2 ArgoCD Application Pattern

Each component becomes a separate ArgoCD Application pointing to its k8s/ overlay:

```yaml
# .gitops/prod/apps/postgrest-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dk-data-fe-postgrest
  namespace: argocd
spec:
  project: dk-data-fe-bootstrap
  source:
    repoURL: https://github.com/data-kinetic/dk-data-fe.git
    targetRevision: main
    path: k8s/postgrest/overlays/prod
  destination:
    server: https://kubernetes.default.svc
    namespace: dk-data-fe-prod
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### 4.3 Bootstrap Integration with dk-alchemy

Add to dk-alchemy repository:
1. `dk-data-fe-bootstrap` AppProject (defines permissions)
2. Bootstrap Application pointing to `.gitops/prod/apps/` in dk-data-fe
3. Doppler project configuration for dk-data-fe secrets

## 5. Implementation Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Git history rewrite causes developer disruption | Medium | Coordinate timing, provide migration guide |
| Doppler unavailability | High | Configure longer resync intervals, local fallback |
| Breaking changes to API access | High | Gradual rollout with JWT migration period |
| CI/CD pipeline changes | Medium | Parallel pipelines during transition |

## 6. Dependencies

### External Dependencies
- dk-alchemy cluster operational with all infrastructure services
- Doppler project `dk-infrastructure` accessible
- MinIO bucket available for data file storage

### Internal Dependencies
- Feature 001-data-layer-postgrest-gitops complete (baseline)
- Team agreement on git history rewrite timing
- JWT rotation plan for existing API consumers

## 7. Research Conclusions

1. **Security**: Use Doppler via DopplerSecret CRDs; no custom secrets management needed
2. **Cleanup**: `git-filter-repo` for history rewrite; MinIO for data file storage
3. **Observability**: OpenTelemetry → Alloy → Mimir/Loki/Tempo; standard Python instrumentation
4. **GitOps**: Migrate from `.gitops/base` pattern to `k8s/` + `.gitops/apps/` pattern

**Ready for Phase 1**: Design artifacts (data-model.md, contracts/, quickstart.md)

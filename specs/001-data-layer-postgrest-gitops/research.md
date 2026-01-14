# Research: Data Layer Enhancement with PostgREST and GitOps

**Feature**: 001-data-layer-postgrest-gitops
**Date**: 2026-01-14

## Research Questions

### 1. PostgREST Configuration for Production K8s

**Question**: How should PostgREST be configured for production deployment in Kubernetes?

**Decision**: Use environment variables for all configuration, with secrets from Doppler Operator.

**Rationale**:
- PostgREST supports full configuration via `PGRST_*` environment variables
- Kubernetes ConfigMaps for non-sensitive settings, Secrets for credentials
- Doppler Operator injects secrets at runtime, avoiding git-stored credentials

**Alternatives Considered**:
- Config file mounted as ConfigMap: More complex, less flexible for environment differences
- Inline in deployment.yaml: Mixes config with infrastructure, harder to manage

**Configuration Pattern**:
```yaml
env:
  - name: PGRST_DB_URI
    valueFrom:
      secretKeyRef:
        name: postgrest-secrets
        key: database-url
  - name: PGRST_DB_SCHEMAS
    value: "api"
  - name: PGRST_DB_ANON_ROLE
    value: "web_anon"
  - name: PGRST_SERVER_PORT
    value: "3000"
  - name: PGRST_DB_POOL
    value: "10"
  - name: PGRST_MAX_ROWS
    value: "1000"
```

### 2. Kustomize Structure for Multi-Environment GitOps

**Question**: How should Kustomize manifests be organized for dev/staging/prod environments?

**Decision**: Base + overlays pattern with environment-specific patches.

**Rationale**:
- Industry standard for GitOps with ArgoCD
- DRY principle: common config in base, differences in overlays
- Easy to audit what differs between environments

**Alternatives Considered**:
- Helm charts: More complex, introduces templating that's harder to read
- Plain manifests per environment: Duplication, drift risk
- Ksonnet: Deprecated

**Structure**:
```
.gitops/
├── base/                    # Shared configuration
│   ├── kustomization.yaml
│   └── postgrest/
│       ├── deployment.yaml  # replicas: 1
│       └── service.yaml
└── overlays/
    ├── dev/
    │   └── kustomization.yaml  # Uses base as-is
    ├── staging/
    │   └── kustomization.yaml  # Maybe 2 replicas
    └── prod/
        ├── kustomization.yaml
        └── patches/
            └── replicas.yaml   # replicas: 3
```

### 3. Batch Job Scheduling in Kubernetes

**Question**: How should batch ingestion jobs be scheduled and triggered?

**Decision**: K8s CronJobs for scheduled runs + FastAPI service for on-demand triggers.

**Rationale**:
- CronJobs are native to K8s, no external dependencies
- Manifests are declarative and GitOps-friendly
- FastAPI provides REST API for manual triggers with OpenAPI docs
- Python K8s client can create Job resources from CronJob templates

**Alternatives Considered**:
- Airflow: Overkill for ~5 data sources, significant infrastructure overhead
- Dagster: Similar to Airflow, better UX but still heavy
- Celery Beat: Requires Redis/RabbitMQ, not K8s-native
- kubectl CLI only: No programmatic access, poor for automation

**Implementation Pattern**:
```python
# FastAPI endpoint to trigger job
@app.post("/jobs/{job_name}/trigger")
async def trigger_job(job_name: str):
    # Use K8s Python client to create Job from CronJob template
    batch_v1 = client.BatchV1Api()
    cronjob = batch_v1.read_namespaced_cron_job(job_name, namespace)
    job = create_job_from_cronjob(cronjob)
    batch_v1.create_namespaced_job(namespace, job)
    return {"job_id": job.metadata.name, "status": "created"}
```

### 4. Data Catalog Schema Design

**Question**: How should the data catalog store metadata for AI retrieval?

**Decision**: Extend existing `meta.data_sources` with new columns and create supporting views.

**Rationale**:
- Builds on existing infrastructure (meta schema already exists)
- PostgreSQL JSONB for flexible column descriptions
- Array type for topic tags enables efficient filtering
- SQL views provide API-ready formats

**Alternatives Considered**:
- Separate catalog database: Unnecessary complexity
- External data catalog (DataHub, Amundsen): Overkill for current scale
- JSON files: Loses query capability, not integrated with data

**Schema Enhancement**:
```sql
ALTER TABLE meta.data_sources ADD COLUMN IF NOT EXISTS
    topic_tags TEXT[] DEFAULT '{}',
    column_descriptions JSONB DEFAULT '{}',
    staleness_threshold_hours INTEGER DEFAULT 24,
    table_size_bytes BIGINT,
    ai_description TEXT;

CREATE TABLE IF NOT EXISTS meta.table_health (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES meta.data_sources(source_id),
    check_timestamp TIMESTAMP DEFAULT NOW(),
    health_status VARCHAR(20), -- 'healthy', 'stale', 'unhealthy'
    null_rate DECIMAL(5,4),
    validation_error_count INTEGER,
    row_count INTEGER,
    freshness_hours INTEGER
);
```

### 5. Health Status Calculation

**Question**: How should table health status be calculated and updated?

**Decision**: SQL function triggered on refresh_log inserts, with periodic scheduled checks.

**Rationale**:
- Real-time updates when data is refreshed
- Scheduled checks catch issues between refreshes
- All logic in SQL, no external service dependencies
- Existing meta.data_quality table can be leveraged

**Alternatives Considered**:
- Python service polling tables: Additional infrastructure, latency
- Application-level health checks: Scattered logic, inconsistent
- External monitoring (Datadog): Cost, complexity for simple checks

**Implementation Pattern**:
```sql
CREATE OR REPLACE FUNCTION meta.calculate_health_status(p_source_id INTEGER)
RETURNS VARCHAR(20) AS $$
DECLARE
    v_freshness_hours INTEGER;
    v_threshold INTEGER;
    v_null_rate DECIMAL;
    v_error_count INTEGER;
BEGIN
    -- Get freshness
    SELECT EXTRACT(EPOCH FROM (NOW() - last_successful_refresh))/3600,
           staleness_threshold_hours
    INTO v_freshness_hours, v_threshold
    FROM meta.data_sources WHERE source_id = p_source_id;

    -- Get quality metrics from latest check
    SELECT null_rate, validation_error_count
    INTO v_null_rate, v_error_count
    FROM meta.table_health
    WHERE source_id = p_source_id
    ORDER BY check_timestamp DESC LIMIT 1;

    -- Determine status
    IF v_freshness_hours > v_threshold * 2 OR v_error_count > 100 THEN
        RETURN 'unhealthy';
    ELSIF v_freshness_hours > v_threshold OR v_null_rate > 0.1 THEN
        RETURN 'stale';
    ELSE
        RETURN 'healthy';
    END IF;
END;
$$ LANGUAGE plpgsql;
```

### 6. Docker Compose Enhancement for Full Stack

**Question**: What services should be included in the local development docker-compose?

**Decision**: PostgreSQL, PostgREST, job-trigger service, with optional Metabase.

**Rationale**:
- Mirrors production architecture locally
- PostgreSQL with all schemas initialized
- PostgREST for API development/testing
- Job trigger for testing batch operations
- Metabase optional (already exists, resource-heavy)

**Alternatives Considered**:
- Minimal (PostgREST only): Can't test batch jobs locally
- Full k3s local: Overkill, slow startup, complex
- Docker-in-Docker for K8s: Brittle, hard to debug

**Service Stack**:
```yaml
services:
  postgres:
    image: postgres:16-alpine
    # Initialize with all schemas

  postgrest:
    image: postgrest/postgrest:v12.2.3
    depends_on: postgres

  job-trigger:
    build: ./src/dk_data/ingestion/batch
    depends_on: postgres
    # For local testing of batch API

  metabase:  # Optional
    image: metabase/metabase:v0.50.26
    profiles: ["metabase"]  # Only start with --profile metabase
```

### 7. ArgoCD Application Configuration

**Question**: How should the ArgoCD Application be configured for automated sync?

**Decision**: Single Application with automated sync, prune, and self-heal enabled.

**Rationale**:
- Full automation matches GitOps principles
- Self-heal prevents manual drift
- Prune removes deleted resources
- Single app simplifies management for this scope

**Alternatives Considered**:
- App-of-Apps pattern: Overkill for single namespace deployment
- Manual sync: Loses GitOps automation benefits
- Separate apps per component: Unnecessary complexity

**Configuration**:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: tavr-data-platform
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/dk-data-fe.git
    targetRevision: main
    path: .gitops/overlays/prod
  destination:
    server: https://kubernetes.default.svc
    namespace: tavr-data
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

## Technology Validation

| Technology | Version | Validated | Notes |
|------------|---------|-----------|-------|
| PostgREST | v12.2.3 | ✅ | Existing in docker-compose |
| PostgreSQL | 16 | ✅ | Existing, supports all features |
| Kustomize | v5.x | ✅ | Built into kubectl |
| ArgoCD | v2.x | ✅ | Standard deployment |
| FastAPI | 0.109+ | ✅ | For job trigger API |
| k3s | v1.29+ | ✅ | Target platform |

## Open Questions (Resolved)

All research questions have been resolved. No blocking unknowns remain.

## References

- [PostgREST Documentation](https://postgrest.org/en/stable/)
- [Kustomize Documentation](https://kustomize.io/)
- [ArgoCD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)
- [Kubernetes CronJob Documentation](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)

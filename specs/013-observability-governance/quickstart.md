# Quickstart: Observability & Platform Governance

**Feature**: 013-observability-governance
**Date**: 2026-02-15

---

## Prerequisites

- Access to the dk-data Kubernetes cluster (staging)
- `kubectl` configured with cluster context
- PostgreSQL client (`psql`) or database access via port-forward
- Python 3.11+ with project dependencies installed (`uv sync`)

---

## Verification Scenarios

### US1: Verify Metrics Endpoint

```bash
# Port-forward to job-trigger pod
kubectl port-forward -n dk-data-staging deploy/job-trigger 8000:8000

# Verify all 10 metric families are emitted
curl -s localhost:8000/metrics | grep -E '^(http_requests_total|http_request_duration|db_query_duration|batch_job_duration|batch_job_records|batch_job_failures|batch_job_last_success|dk_data_source_last_refresh|dk_data_source_row_count|dk_data_source_staleness)'

# Expected: at least 10 distinct metric family lines
```

### US1: Verify ServiceMonitor Deployment

```bash
# Check ServiceMonitors exist in cluster
kubectl get servicemonitors -n dk-data-staging

# Expected output:
# NAME                    AGE
# dk-data-postgrest       Xs
# dk-data-job-trigger     Xs

# Check PodMonitors exist
kubectl get podmonitors -n dk-data-staging

# Expected output:
# NAME                          AGE
# dk-data-cronjobs              Xs
# dk-data-molecule-cronjobs     Xs

# Check PrometheusRules exist
kubectl get prometheusrules -n dk-data-staging

# Expected output:
# NAME              AGE
# dk-data-alerts    Xs
```

### US1: Verify Prometheus Scraping

```bash
# Port-forward to Prometheus/Mimir (in infra namespace)
kubectl port-forward -n infra svc/mimir 9009:9009

# Query for job-trigger metrics
curl -s 'http://localhost:9009/prometheus/api/v1/query?query=http_requests_total{namespace="dk-data-staging"}' | python3 -m json.tool

# Expected: non-empty result with data points
```

### US2: Verify PostgREST Probe

```bash
# Check probe resource exists
kubectl get probes -n dk-data-staging

# Or if using ServiceMonitor approach, verify PostgREST health
kubectl port-forward -n dk-data-staging svc/postgrest 3000:3000
curl -s localhost:3000/health

# Expected: JSON response with connection pool status
```

### US3: Verify Audit Logging

```bash
# Make an authenticated API request
export TOKEN=$(python3 -c "
import jwt, time
print(jwt.encode({'role':'api_user','sub':'test-user','exp':int(time.time())+3600}, 'your-jwt-secret', algorithm='HS256'))
")

# Query via PostgREST (triggers PostgreSQL audit function)
curl -H "Authorization: Bearer $TOKEN" https://data.staging.behaviorlabs.ai/molecules?limit=1

# Query the audit log
curl -H "Authorization: Bearer $TOKEN" 'https://data.staging.behaviorlabs.ai/audit_log?order=timestamp.desc&limit=5'

# Expected: Recent audit entries including the molecules query
```

### US3: Verify Ingestion Audit

```bash
# Trigger a CronJob manually
kubectl create job --from=cronjob/fetch-pubmed test-audit-pubmed -n dk-data-staging

# Wait for completion
kubectl wait --for=condition=complete job/test-audit-pubmed -n dk-data-staging --timeout=120s

# Query audit log for ingestion events
curl -H "Authorization: Bearer $TOKEN" 'https://data.staging.behaviorlabs.ai/audit_log?category=eq.data_source&order=timestamp.desc&limit=5'

# Expected: Audit entry with source=cronjob, action=source_synced
```

### US4: Verify Migration Runner

```bash
# Run migration runner locally (with DB connection)
export DATABASE_URL="postgresql://user:pass@localhost:5432/dk_data"
python -m dk_data.scripts.run_migrations

# Expected output:
# Migration 001_catalog_health_jobs.sql: SKIPPED (already applied)
# Migration 002_role_restrictions.sql: SKIPPED (already applied)
# ... (all 26 skipped if baseline was run)
# No pending migrations.

# Run again — idempotent
python -m dk_data.scripts.run_migrations
# Expected: "No pending migrations."

# Check migration status via API
curl -H "Authorization: Bearer $TOKEN" 'https://data.staging.behaviorlabs.ai/migration_status?order=version'

# Expected: All 26+ migrations listed with applied_at timestamps
```

### US4: Verify Baseline Command

```bash
# For existing databases with manually-applied migrations
python -m dk_data.scripts.run_migrations --baseline

# Expected output:
# Baseline mode: marking 26 migrations as applied without executing
# Migration 001_catalog_health_jobs.sql: BASELINED
# ... (all 26 baselined)
# Baseline complete.
```

### US5: Verify Data Classification

```bash
# Query data classification via API
curl -H "Authorization: Bearer $TOKEN" 'https://data.staging.behaviorlabs.ai/data_classification?order=classification,schema_name'

# Expected: All tables classified (public, internal, pii, confidential)
# PII tables: raw.orcid with pii_fields=['given_names','family_name','credit_name','biography']

# Verify PII table identification
curl -H "Authorization: Bearer $TOKEN" 'https://data.staging.behaviorlabs.ai/data_classification?classification=eq.pii'

# Expected: raw.orcid entry with pii_fields listed
```

### US5: Verify Retention Policy

```bash
# Run the extended purge with retention policy
python -m dk_data.scripts.purge_history --dry-run

# Expected: Shows what would be purged based on retention_days per classification
# - scoring.score_history: records older than 730 days
# - raw.orcid: records older than 365 days
# - meta.api_audit_log (access): records older than 365 days
```

---

## Test Commands

```bash
# Run all new tests
pytest tests/test_migration_runner.py tests/test_audit_middleware.py tests/test_data_classification.py tests/test_api_views_governance.py -v

# Run full test suite
pytest tests/ -q

# Validate K8s manifests
kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null
kubectl kustomize k8s/overlays/prod --enable-helm > /dev/null
```

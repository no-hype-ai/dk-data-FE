# Quickstart: Platform Stabilization

**Feature Branch**: `010-platform-stabilization`

## Prerequisites

- Access to the k3d cluster (`kubectl` configured)
- GitHub PAT with `read:packages` scope
- Doppler CLI access to `dk-data-fe` project
- MinIO credentials for the `infra` namespace instance

## Verification Steps (Post-Implementation)

### 1. Verify Ingestion Pipelines

```bash
# Check job-trigger pod is Running (not ImagePullBackOff)
kubectl get pods -n dk-data-staging -l app=job-trigger

# Check all CronJobs have recent successful runs
kubectl get cronjobs -n dk-data-staging
# LAST SCHEDULE column should show recent timestamps

# Check for any failed jobs
kubectl get jobs -n dk-data-staging --field-selector=status.successful=0
```

### 2. Verify Database Backups

```bash
# Check backup CronJobs exist
kubectl get cronjobs -n dk-data-staging -l app=pg-backup

# Check latest backup job succeeded
kubectl get jobs -n dk-data-staging -l app=pg-backup --sort-by=.metadata.creationTimestamp

# List backups in MinIO (port-forward MinIO first)
kubectl port-forward -n infra svc/minio 9000:9000 &
mc alias set local http://localhost:9000 $MINIO_ACCESS_KEY $MINIO_SECRET_KEY
mc ls local/postgres-backups/dk-data-staging/daily/
```

### 3. Verify Security Hardening

```bash
# Scan for hardcoded credentials (should return zero matches)
grep -rn "postgrest_secret_change_me" src/dk_data/sql/
grep -rn "PASSWORD '" src/dk_data/sql/

# Verify database name consistency
grep -rn "edwards_tavr" docker-compose.yml src/dk_data/sql/init_database.sql
# Should return zero matches
```

### 4. Verify Test Coverage

```bash
# Run tests with coverage locally
pip install -e ".[dev]"
pytest tests/ -v --cov=src/dk_data --cov-report=term-missing --cov-fail-under=15

# Check CI passes on a test PR
gh pr checks <PR_NUMBER>
```

### 5. Verify Repository Hygiene

```bash
# Verify raw data is gitignored
git status src/dk_data/data/raw/
# Should show nothing (files are ignored)

# Verify .gitignore entry exists
grep "data/raw" .gitignore
```

### 6. Verify Observability

```bash
# Check ServiceMonitors exist
kubectl get servicemonitors -n dk-data-staging

# Check Alloy is receiving telemetry
kubectl logs -n infra -l app=alloy --tail=50 | grep -E "(otlp|scrape)"

# Check PrometheusRules exist
kubectl get prometheusrules -n dk-data-staging
```

### 7. Verify Issue Tracker Cleanup

```bash
# Count open issues (should be ~35 after closing ~15)
gh issue list --state open --limit 100 | wc -l
```

## Local Development Changes

After this feature, local development setup changes:

1. **Database name**: Default is now `dk_data` (was `edwards_tavr`). Update your `.env` file:
   ```
   POSTGRES_DB=dk_data
   ```

2. **New dev dependencies**: Install with `pip install -e ".[dev]"` to get `pytest-cov` and `responses`

3. **Raw data files**: No longer tracked by git. Fetch via the ingestion pipeline:
   ```bash
   make fetch-cms  # or equivalent make target
   ```

4. **Running tests**: Coverage is now reported automatically:
   ```bash
   pytest tests/  # --cov flags are in pyproject.toml
   ```

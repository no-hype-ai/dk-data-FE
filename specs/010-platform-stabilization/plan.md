# Implementation Plan: Platform Stabilization

**Branch**: `010-platform-stabilization` | **Date**: 2026-02-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-platform-stabilization/spec.md`

## Summary

Stabilize the dk-data-fe platform by fixing broken ingestion pipelines (GHCR credentials + DNS), implementing automated database backups to MinIO, removing hardcoded credentials, standardizing database naming, establishing a test coverage baseline with pytest-cov, removing 182MB of raw CSV data from git, enabling the observability stack (Prometheus CRDs + Grafana Alloy), and closing ~15 resolved GitHub issues. Image promotion from staging to production is automated via `crane tag` after staging validation succeeds.

## Technical Context

**Language/Version**: Python 3.11+, SQL (PostgreSQL 16.4), YAML (Kubernetes manifests), Bash (backup/setup scripts)
**Primary Dependencies**: FastAPI, PostgREST v12.2.3, psycopg2-binary, pytest-cov (new), responses (new), Kustomize, crane (new CI tool)
**Storage**: PostgreSQL 16.4 (shared infra namespace), MinIO (backup storage, infra namespace)
**Testing**: pytest + pytest-cov + responses (mocked HTTP), pytest-postgresql
**Target Platform**: Kubernetes (k3d on macOS/Proxmox), GitHub Actions CI
**Project Type**: Single project (data platform with API layer)
**Performance Goals**: All CronJobs complete within 1h (daily) / 2h (weekly); backup restore < 30 minutes
**Constraints**: Single k3d node, shared PostgreSQL instance, Doppler for secrets
**Scale/Scope**: ~88K lines Python, 5 CronJobs, 2 deployments (PostgREST, job-trigger), 50 open issues → ~35

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No project constitution defined (template only). No gates to evaluate. Proceeding.

**Post-Phase 1 re-check**: No violations. The plan follows existing project conventions (Kustomize overlays, Doppler secrets, PostgreSQL, GitHub Actions).

## Project Structure

### Documentation (this feature)

```text
specs/010-platform-stabilization/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Technical research findings
├── data-model.md        # Phase 1: Entity and configuration changes
├── quickstart.md        # Phase 1: Verification guide
├── contracts/           # Phase 1: Interface contracts
│   ├── backup-cronjob.yaml
│   └── ci-pipeline.yaml
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
# Files MODIFIED by this feature
src/dk_data/sql/init_database.sql          # Remove hardcoded password, parameterize
docker-compose.yml                          # Standardize DB name to dk_data
pyproject.toml                              # Add pytest-cov, responses, coverage config
.gitignore                                  # Add src/dk_data/data/raw/
.github/workflows/ci.yaml                   # Add coverage reporting
.github/workflows/build-push.yaml           # Use kustomize edit instead of sed
k8s/base/kustomization.yaml                 # Uncomment observability resources
k8s/base/networkpolicy.yaml                 # Add MinIO egress rule
k8s/base/ingestion/job-trigger-deployment.yaml  # Placeholder image tag
k8s/overlays/staging/kustomization.yaml     # Add images: transformer
k8s/overlays/prod/kustomization.yaml        # Add images: transformer

# Files CREATED by this feature
.github/workflows/promote-to-prod.yaml     # NEW: Image promotion workflow
k8s/base/backup/pg-backup-daily.yaml       # NEW: Daily backup CronJob
k8s/base/backup/pg-backup-weekly.yaml      # NEW: Weekly backup CronJob
k8s/base/backup/pg-backup-verify.yaml      # NEW: Backup verification CronJob
k8s/base/backup/pg-backup-configmap.yaml   # NEW: Backup script ConfigMap
k8s/base/backup/minio-credentials.yaml     # NEW: MinIO credential secret template
tests/test_imports.py                       # NEW: Import smoke tests
tests/test_pydantic_models.py              # NEW: Model validation tests
tests/test_fastapi_endpoints.py            # NEW: Job-trigger API tests
tests/test_fetchers.py                     # NEW: Mocked fetcher tests

# Files REMOVED from tracking (not deleted)
src/dk_data/data/raw/*.csv                 # Untracked via git rm --cached
```

**Structure Decision**: Existing single-project layout preserved. New files follow established conventions: K8s manifests in `k8s/base/`, tests in `tests/`, workflows in `.github/workflows/`.

## Complexity Tracking

No constitution violations to justify. All changes follow existing project patterns.

# Implementation Plan: Production Readiness for dk-data-fe

**Branch**: `002-production-readiness` | **Date**: 2026-01-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-production-readiness/spec.md`

## Summary

Transform dk-data-fe from MVP to production-ready by:
1. **Security (P0-P1)**: Remove hardcoded credentials, integrate with dk-alchemy Doppler secrets, strengthen JWT authentication
2. **Codebase Cleanup (P1)**: Eliminate 18 duplicate files, remove 74MB committed data, consolidate to single Makefile
3. **Observability (P2)**: Integrate with dk-alchemy Mimir/Loki/Tempo stack via OpenTelemetry
4. **GitOps (P2)**: Restructure for ArgoCD external app pattern following dk-alchemy conventions

## Technical Context

**Language/Version**: Python 3.11+, SQL (PostgreSQL 16)
**Primary Dependencies**: SQLMesh, PostgREST v12.x, FastAPI, psycopg2, Pydantic, OpenTelemetry
**Storage**: PostgreSQL 16 (CNPG in production), MinIO for data files
**Testing**: pytest with pytest-postgresql
**Target Platform**: Kubernetes (dk-alchemy cluster), Docker Compose (local dev)
**Project Type**: Data platform (single project structure)
**Performance Goals**: API <100ms p95, data freshness <48 hours, ingestion jobs <5 minutes
**Constraints**: Zero secrets in git, <10MB repository size, ArgoCD sync <5 minutes
**Scale/Scope**: ~20 data sources, 3 environments (dev/staging/prod)

## Constitution Check

*GATE: Constitution not yet configured for this project. Proceeding with standard practices.*

- ✅ No constitution violations detected (template-only constitution.md)
- ✅ Standard Python project structure
- ✅ Kustomize base/overlay pattern already in use
- ✅ Tests directory exists (requires expansion)

## Project Structure

### Documentation (this feature)

```text
specs/002-production-readiness/
├── plan.md              # This file
├── research.md          # Phase 0: Technical analysis and recommendations
├── data-model.md        # Phase 1: DopplerSecret, observability config schemas
├── quickstart.md        # Phase 1: Migration runbook
├── contracts/           # Phase 1: API contracts, alerting rules
└── tasks.md             # Phase 2: Implementation tasks (/speckit.tasks)
```

### Source Code (repository root)

```text
# Current structure (to be cleaned up)
src/dk_data/
├── __init__.py
├── ingestion/
│   ├── batch/           # FastAPI job-trigger service
│   ├── fetchers/        # Data source fetchers
│   ├── sources/         # Source configurations
│   ├── services/        # CMS catalog service
│   └── utils/           # Database, retry, validators
├── claude_sdk/          # AI enrichment (scoring_agent, enrichment)
├── scripts/             # CANONICAL location for all scripts
│   ├── catalog_refresh.py
│   ├── check_freshness.py
│   ├── load_targeting_data.py
│   └── ...
├── sql/                 # CANONICAL location for SQL
│   ├── init_database.sql
│   ├── migrations/
│   └── targeting_tables.sql
└── sqlmesh/             # SQLMesh models and config

# Directories to REMOVE (duplicates)
scripts/                 # Remove - duplicates src/dk_data/scripts/
data/                    # Remove from git - store in MinIO
logs/                    # Remove from git - gitignore

# GitOps structure (already exists, needs enhancement)
.gitops/
├── argocd/
│   └── application.yaml   # Update for dk-alchemy external app pattern
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── postgrest/
│   ├── ingestion/
│   └── catalog/
└── overlays/
    ├── dev/
    ├── staging/
    └── prod/

# New additions for production readiness
.gitops/base/
├── secrets/               # NEW: DopplerSecret CRDs
│   └── doppler-secret.yaml
├── observability/         # NEW: ServiceMonitor, LogPipeline
│   ├── service-monitor.yaml
│   └── grafana-dashboard.yaml
└── network/               # NEW: NetworkPolicy, IngressRoute
    ├── network-policy.yaml
    └── ingress-route.yaml

tests/
├── contract/              # NEW: API contract tests
├── integration/           # NEW: Database integration tests
└── unit/                  # Existing pytest tests
```

**Structure Decision**: Single project structure. The existing `src/dk_data/` layout is retained with cleanup of duplicate directories. GitOps manifests in `.gitops/` follow Kustomize base/overlay pattern matching dk-alchemy conventions.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Git history rewrite | Remove 74MB data + secrets from history | Shallow clone insufficient - secrets remain discoverable |
| Multiple overlays | Dev/staging/prod environments | Single manifest insufficient for resource differentiation |

## Generated Artifacts

### Phase 0: Research

- **[research.md](./research.md)**: Technical analysis covering security, cleanup, observability, and GitOps

### Phase 1: Design

- **[data-model.md](./data-model.md)**: Kubernetes resource schemas, observability config models, application configuration
- **[quickstart.md](./quickstart.md)**: Step-by-step migration runbook with verification checklists

### Phase 1: Contracts

| Contract | Purpose | Implements |
|----------|---------|------------|
| [contracts/doppler-secret.yaml](./contracts/doppler-secret.yaml) | Secrets synchronization from Doppler | FR-001, FR-002, FR-006 |
| [contracts/alert-rules.yaml](./contracts/alert-rules.yaml) | Prometheus alerting rules | FR-017 |
| [contracts/service-monitor.yaml](./contracts/service-monitor.yaml) | Metrics scrape configuration | FR-014 |
| [contracts/network-policy.yaml](./contracts/network-policy.yaml) | Zero-trust pod networking | FR-020 |
| [contracts/ingress-route.yaml](./contracts/ingress-route.yaml) | External access with rate limiting | FR-005 |

## Implementation Phases

| Phase | Focus | Duration | Dependencies |
|-------|-------|----------|--------------|
| 1 | Security Hardening | 2 days | Doppler access, dk-alchemy cluster |
| 2 | Codebase Cleanup | 2 days | Team coordination for git rewrite |
| 3 | Observability Integration | 2 days | Phase 1 complete |
| 4 | GitOps Restructuring | 2 days | Phase 2 complete |

**Total Estimated Duration**: 8 working days

## Success Criteria Mapping

| Success Criteria | Verification Method | Contract/Artifact |
|------------------|---------------------|-------------------|
| SC-001: Zero secrets in git | `gitleaks detect` | - |
| SC-002: Repo <10MB | `git count-objects -vH` | - |
| SC-003: Zero duplicates | File diff check | - |
| SC-004: Metrics in Grafana <60s | Manual verification | service-monitor.yaml |
| SC-005: ArgoCD sync <5min | Sync timing test | - |
| SC-006: App starts <30s | Deployment timing | doppler-secret.yaml |
| SC-007: 401 on protected endpoints | `curl` test | ingress-route.yaml |
| SC-008: CI passes all checks | GitHub Actions | - |

## Next Steps

Run `/speckit.tasks` to generate detailed implementation tasks in `tasks.md`.

## Risk Mitigation

| Risk | Mitigation | Owner |
|------|------------|-------|
| Git history rewrite disrupts team | Schedule during low-activity period, notify all developers | Tech Lead |
| Doppler unavailability | Configure 5-min resync, document fallback procedure | Platform Team |
| Breaking API changes | JWT migration period with both auth methods | Backend Team |

---

**Plan Status**: ✅ Complete - Ready for `/speckit.tasks`

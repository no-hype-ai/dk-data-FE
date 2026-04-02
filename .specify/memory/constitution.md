# DK Data FE Constitution

## Core Principles

### I. GitOps Deployment Model

All infrastructure and application deployments MUST follow GitOps principles:

- Infrastructure changes MUST be declarative YAML in the `k8s/` directory
- Deployments MUST use Kustomize base/overlay pattern for environment differentiation
- ArgoCD MUST be the single source of truth for cluster state
- Manual `kubectl apply` for production changes is FORBIDDEN
- All secrets MUST be managed through Doppler (no `.env` files committed)
- Monitoring config MUST reside in `grafana/dashboards/` and `grafana/alerts/` per org standard

**Rationale**: Provides audit trails, rollback capability, and eliminates configuration drift.

### II. Environment Parity

Local, staging, and production environments MUST maintain structural parity:

- All apps deployed to staging MUST also have production k8s configurations
- Environment differences MUST be limited to: replica counts, resource limits, domains, and secrets
- Database schemas MUST be identical across environments (managed by SQL migrations)

**Rationale**: Prevents environment-specific bugs and ensures staging accurately reflects production.

### III. Observability by Default

All deployable services MUST be observable:

- Prometheus metrics MUST be emitted via `/metrics` endpoint on all long-running services
- CronJob execution results MUST be recorded in the database and exposed via the job-trigger's metrics endpoint
- Health check endpoints (`/health`) MUST be exposed
- OpenTelemetry traces MUST be emitted for cross-service calls
- Grafana dashboards and alerts MUST be maintained as code in `grafana/`
- All metrics defined in `src/dk_data/observability/metrics.py` MUST be populated (no dead metrics)

**Rationale**: Production issues require data; observability enables rapid diagnosis and resolution.

### IV. Specification-Driven Development

Features MUST follow the Speckit workflow before implementation:

- Feature work MUST start with `/speckit.specify` to create specification
- Specifications MUST be approved before planning begins
- Plans MUST be created via `/speckit.plan` before coding
- Tasks MUST be generated via `/speckit.tasks` from approved plans
- Significant deviations from approved plans MUST be documented and justified

**Rationale**: Upfront design reduces rework and ensures stakeholder alignment.

### V. Medallion Architecture Integrity

Data MUST flow through the medallion pipeline (raw → bronze → silver → gold) with clear boundaries:

- Each layer MUST have its own schema prefix (`raw.*`, `mol_bronze.*`, `mol_silver.*`, `mol_gold.*`, etc.)
- Cross-layer dependencies MUST be explicit (transforms reference upstream layer only)
- Processing status flags (`processed_to_bronze`, `processed_to_silver`) MUST be maintained
- Entity resolution MUST produce canonical records in silver with confidence scores

**Rationale**: Clean layer separation enables independent evolution, debugging, and data lineage tracking.

### VI. No Dead Infrastructure

Kubernetes manifests, monitoring configs, and CI/CD resources MUST be functional:

- No CRDs that depend on absent operators (e.g., PrometheusRule without Prometheus Operator)
- No ConfigMaps referencing non-existent sidecars or provisioners
- Orphaned resources MUST be deleted, not commented out
- Monitoring delivery MUST use the org-standard uplift pattern (product repo → dk-alchemy → Grafana)

**Rationale**: Dead infrastructure creates false confidence and confusion during incidents.

## Technology Constraints

### Required Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Language | Python 3.11+ | All application code |
| API Framework | FastAPI | job-trigger service |
| Database | PostgreSQL 16.4 | CloudNativePG in k8s, psycopg2-binary for sync, asyncpg for async |
| Metrics | prometheus-client | `/metrics` endpoint, Alloy scrapes every 30s |
| Tracing | OpenTelemetry SDK | OTEL push to Alloy for traces from CronJob pods |
| Transforms | SQLMesh | Medallion layer transformations |
| Logging | structlog | Structured JSON logging |
| Secrets | Doppler | No local .env files |
| Infrastructure | K3s (remote) | ArgoCD for GitOps |
| Monitoring | Grafana + Mimir + Loki + Tempo | Via dk-alchemy sync pipeline |

### Forbidden Patterns

- Prometheus Operator CRDs (ServiceMonitor, PodMonitor, PrometheusRule) — no operator in cluster
- Hardcoded secrets or credentials
- Monitoring config in `monitoring/` directory (must use `grafana/`)
- Direct Grafana API provisioning bypassing dk-alchemy
- Metrics defined in code but never populated (dead metrics)
- Manual `kubectl apply` for production

## Development Workflow

### Branch Conventions

- Feature branches: `NNN-feature-name` (created by Speckit scripts)
- Main branch: Production-ready code
- Staging branch: Pre-production validation

### Quality Gates

Before merging to main:

1. All CI checks MUST pass (lint, type-check, tests)
2. Specification and plan documentation MUST be complete
3. Database migrations MUST be backwards-compatible
4. `kubectl kustomize k8s/base/` MUST succeed with no errors
5. No orphaned monitoring CRDs in kustomize output

### Testing Requirements

- Tests are OPTIONAL by default (only when explicitly requested)
- When tests ARE required:
  - Unit tests for business logic
  - Integration tests for API endpoints
  - Metrics endpoint verification tests

## Governance

This constitution establishes non-negotiable principles for the DK Data FE platform.

### Amendment Process

1. Propose changes via feature branch with updated constitution
2. Document rationale for each change
3. Version increments follow semantic versioning:
   - **MAJOR**: Principle removals or redefinitions
   - **MINOR**: New principles or expanded guidance
   - **PATCH**: Clarifications and wording improvements

### Compliance

- All PRs MUST verify compliance with relevant principles
- Plan templates include Constitution Check gate
- Violations require documented justification in Complexity Tracking

### Runtime Guidance

For implementation details beyond this constitution, refer to:

- `CLAUDE.md` - Development commands and architecture overview
- `docs/` - Detailed operational documentation

**Version**: 1.0.0 | **Ratified**: 2026-04-02 | **Last Amended**: 2026-04-02

# Research: Observability & Platform Governance

**Feature**: 013-observability-governance
**Date**: 2026-02-15

---

## R1: ServiceMonitor Label Compatibility

**Decision**: Existing ServiceMonitor manifests are correctly configured and ready to deploy.

**Rationale**: All label selectors match their target services:
- `dk-data-postgrest` ServiceMonitor selects `app: postgrest` → matches PostgREST Service
- `dk-data-job-trigger` ServiceMonitor selects `app: job-trigger` → matches job-trigger Service
- PodMonitors for CronJobs select `app.kubernetes.io/component: batch-job` → needs CronJob label audit
- All use `release: mimir` metadata label for Prometheus Operator discovery

**Alternatives considered**:
- Re-creating ServiceMonitors from scratch — unnecessary, existing ones are well-structured
- Using Grafana Alloy scrape config directly — bypasses Prometheus Operator; less portable

**Open risk**: Cluster's `serviceMonitorSelector` must match `release: mimir`. This is configured in dk-alchemy, not this repo. Verify during deployment.

**PostgREST scrape path**: ServiceMonitor scrapes PostgREST at `/` (root). PostgREST v12.2.3 does not expose native Prometheus metrics — the existing ServiceMonitor configuration may not produce useful metrics. This needs verification; if PostgREST doesn't serve Prometheus format at `/`, the PostgREST ServiceMonitor should be removed in favor of blackbox probing (US2).

---

## R2: Audit Logging Architecture

**Decision**: Two-layer audit approach — application middleware on job-trigger + PostgreSQL audit function on API views.

**Rationale**:
- PostgREST is stateless with no middleware hooks — cannot intercept requests at the application level
- Job-trigger is FastAPI with existing middleware stack (SecurityHeaders, RequestTracking, CacheControl) — natural insertion point for audit middleware
- Existing audit log models in `src/dk_data/models/application/audit_log.py` provide 16 action types and 8 categories
- Existing `meta.refresh_log` already tracks ingestion operations — extend rather than replace

**Architecture**:

| Layer | Coverage | Mechanism | Target Table |
|-------|----------|-----------|-------------|
| HTTP (job-trigger) | All FastAPI API calls | AuditLoggingMiddleware (new) | `meta.api_audit_log` (new) |
| Database (PostgREST) | All API view queries via PostgREST | PostgreSQL audit function + trigger on api.* views | `meta.api_audit_log` |
| Operational | Data ingestion jobs | Existing refresh_log writes | `meta.refresh_log` (existing) |

**PostgREST audit approach**: Use PostgreSQL's `current_setting('request.jwt.claims')` inside a trigger function on API views. PostgREST sets this GUC variable for every request, providing the JWT claims (role, sub) at the database level. This captures who queried which view without needing application-level middleware.

**Alternatives considered**:
- Reverse proxy sidecar (Nginx) in front of PostgREST — adds operational complexity, another container to maintain
- PostgreSQL `log_statement = 'all'` — too noisy, not structured, performance cost
- pgaudit extension — heavyweight, requires PostgreSQL extension installation, overkill for view-level access logging

---

## R3: Migration Runner Strategy

**Decision**: Build a lightweight custom Python migration runner with `meta.schema_migrations` tracking table.

**Rationale**:
- 26 existing migrations using pure SQL with `NNN_description.sql` naming convention
- All migrations are idempotent (IF NOT EXISTS patterns) — safe for re-runs
- No ORM — Alembic/SQLAlchemy migration tools are misaligned
- Custom runner is ~100 lines of Python with psycopg2 (already a dependency)
- Integrates naturally into the K8s db-init-job as a final step

**Migration naming**: `NNN_description.sql` (3-digit prefix, gaps allowed for feature spacing)
- Current range: 001-066 (26 files, intentional gaps)

**Baseline strategy**: For existing databases with migrations already applied manually:
- Runner creates `meta.schema_migrations` tracking table
- `--baseline` flag marks all existing migrations as applied without executing them
- Normal mode executes only migrations not in the tracking table

**K8s integration**: Add migration runner as final step in `db-init-job.yaml` after schema/role creation

**Alternatives considered**:
- Alembic — requires SQLAlchemy ORM, heavyweight for pure SQL migrations
- Yoyo — lightweight but adds another dependency; custom is simpler
- DBmate — separate binary, requires Docker image changes
- Flyway — Java-based, incompatible with Python stack

---

## R4: Data Classification Inventory

**Decision**: 4-tier classification scheme based on data sensitivity analysis of all 33 data sources across 12 schemas.

**Rationale**: Analysis of all tables reveals distinct sensitivity levels:

| Tier | Classification | Schemas/Tables | Access |
|------|---------------|----------------|--------|
| 1 | CONFIDENTIAL | `scoring.*`, `mart.*`, `staging.hospitals/certifications/tavr_volumes` | `analyst` only |
| 2 | INTERNAL-PII | `raw.orcid` (researcher names, affiliations, identifiers) | `api_user`, `analyst` |
| 3 | INTERNAL | CI tables (`raw.pubmed`, `raw.openalex_ci`, etc.) — published author names in JSONB | `api_user`, `analyst` |
| 4 | PUBLIC | All molecule/drug/protein reference data, `mol_*` schemas, `api.*` views | All authenticated roles |

**PII inventory**:
- `raw.orcid`: given_names, family_name, credit_name, biography, current_affiliations, external_ids — researcher PII
- `raw.pubmed`, `raw.openalex_ci`, `raw.journal_rss`, `raw.cochrane_reviews`: author names in JSONB — published, publicly available
- `raw.uspto_patents`, `raw.epo_patents`: inventor/assignee names in JSONB — published, publicly available

**Retention policy defaults**:

| Data Type | Retention | Rationale |
|-----------|-----------|-----------|
| Raw ingestion data (public) | 2 years rolling | Balance storage vs. historical analysis |
| ORCID researcher PII | 1 year rolling | Minimize PII exposure; re-fetch quarterly |
| Hospital/TAVR data | Active + 1 year | Business-critical, regulatory retention |
| Scoring history | 2 years rolling (existing purge_history.py default) | Already implemented |
| Audit logs (access) | 1 year | Standard access log retention |
| Audit logs (data changes) | 7 years | Compliance-grade retention |
| Molecule reference data | Perpetual | Scientific reference, permanent value |

**purge_history.py status**: Currently only purges `scoring.score_history`. Needs extension to support multi-table retention via configuration.

---

## R5: PostgREST Health Probing

**Decision**: Use Prometheus blackbox-exporter Probe CRD (if available in cluster) or a lightweight CronJob-based health check.

**Rationale**: PostgREST v12.2.3 exposes a `/health` endpoint that returns connection pool status. The existing ServiceMonitor for PostgREST scrapes at `/` which likely returns PostgREST's root response (not Prometheus format). For availability monitoring, a Probe resource or simple HTTP check is more appropriate.

**Approach**: Create a Kubernetes Probe CRD resource targeting `http://postgrest.dk-data-staging:3000/health` (and prod equivalent). If blackbox-exporter is not deployed in the cluster, fall back to updating the existing PostgREST ServiceMonitor to use a valid metrics path, or accept that PostgREST monitoring is limited to Kubernetes liveness/readiness probes already in place.

**Alternatives considered**:
- PostgREST sidecar exporter — too heavyweight for availability monitoring
- Custom metrics endpoint via nginx sidecar — adds complexity
- Traefik IngressRoute metrics — available but limited to L7 metrics, no PostgREST-specific health

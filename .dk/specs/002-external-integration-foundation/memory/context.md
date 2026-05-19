# Feature Context — external-integration-foundation

**Branch**: `feature/002-external-integration-foundation`
**Started**: 2026-04-13
**Source brief**: `/Users/pschloz/Desktop/DataKinetic/Cross-Project-Planning/dk data fe/06-plan/dk-data-external-integration-plan.md`

## Active Tags

Inherited from `.dk/memory/tags.md`:

- `[IDMPT]`, `[GITOP]`, `[SECRT]`, `[TESTE]`, `[WALMX]`, `[DSN]`, `[JOBLK]`, `[PGBOU]`, `[NOLOG]`, `[BRKR]`

**New activations for this feature**:

- `[ZVAL]` — new FastAPI resolve wrapper routes use Pydantic bodies
- `[VERSN]` — client package SemVer enforced
- `[RBAC]` — router-level `Depends(verify_jwt)` on `/data-platform`
- `[AUDIT]` — metering proxy audit-logs every request

## Key Constraints

- **Migration order**: 215 → 216 → 217 → 218 → 220 (216 depends on 215; 218 runs last)
- **Hard sequence**: provision metering-proxy API keys BEFORE migration 218 runs, or every consumer 401s on the day of the drop
- **Verified fact**: `mol_silver.drug_label_sections` does NOT exist; `boxed_warning` is an inline column on `mol_silver.drug_labels`
- **Verified fact**: k8s probes are TCP-only (deployment.yaml lines 130–146) — no `api.health` carve-out needed
- **Verified fact**: `mol_api` is already in `PGRST_DB_SCHEMAS` in k8s production; only standalone/docker configs are stale
- **Verified fact**: `analyst` and `api_user` already have SELECT on `mol_api.*` via `db-init-job.yaml` lines 206–212
- **Rollback policy**: 218 rollback restores MINIMUM grants only (api.health + api.data_catalog) — not the full legacy grant set
- **Alias sunset**: 30 days after last telemetry-verified consumer migration to the prefixed names
- `[WALMX]`: migrations are metadata-only; no WAL concern
- `[DSN]`: all new Python DB conns via `build_dsn()`

## Important Context

### Critical file paths

**dk-data-FE**:
- `src/dk_data/api/routes/data_platform.py` — add router-level JWT dep
- `src/dk_data/api/dependencies/auth.py` — NEW (US-15)
- `src/dk_data/observability/metrics.py` — 78 definitions, 38 dead; wire up or delete
- `src/dk_data/services/data_platform/pipeline_monitoring.py` line 139 — `record_pipeline_processing_duration()` helper exists but is never called
- `src/dk_data/ingestion/utils/build_model_lineage.py` lines 38–209 — add `mol_api` + `ip_api` to `_SKIP_SCHEMAS`
- `src/dk_data/sql/migrations/215–220` — NEW
- `src/dk_data/sql/post_sqlmesh/055_postgrest_hub_grants.sql` — strip `web_anon` block
- `k8s/apps/postgrest/base/configmap.yaml` line 12 — unset `PGRST_DB_ANON_ROLE`
- `k8s/apps/metering-proxy/base/configmap.yaml` — provision api_keys for 5 consumers, scope `internal`
- `k8s/apps/infrastructure/base/db-init-job.yaml` lines 113–123 — remove `web_anon` creation
- `grafana/dashboards/dk-data-transformations.json` lines 776 + 816 — reference dead metrics
- `k8s/apps/cronjobs/base/` — 25 YAML files to delete

**Consuming apps** (separate repos):
- `behavior-labs-ai/apps/admin/lib/dk-data/postgrest-client.ts` — 19 methods to migrate
- `behavior-labs-ai/apps/api/src/competitive-intel/sources/dk-data-fe.client.ts` lines 74–98 — remove localhost fallback
- `behavior-labs-ai/apps/api/src/research/agents/{molecule-profile,safety-profile,clinical-trial,regulatory-status}.agent.ts` — 4 agents
- `ground-truth-charlie/src/lib/adapters/{pubmed,openalex}-adapter.ts` — replace with client calls
- `trials-predictor/app/backend/sqlmesh_project/macros/identifier_utils.py` — add client resolve

### Autonomous decisions made during dk.auto

See `auto-decisions.json` at feature dir root. Top 5:
1. Client ships in TS + Python simultaneously (not phased)
2. L2 cache: Redis in production, SQLite in dev
3. Telemetry per-call in v0.1, batching deferred to v1.1
4. Rollback restores minimum grants only
5. 30-day telemetry-gated deprecated-alias window

## Open Questions

- Infrastructure team sign-off on capacity: Loki headroom for ~7M events/day, connection pool for metering proxy credential minting
- Platform API team to provision metering-proxy keys for 5 consumers
- Each consuming-app team to coordinate cutover in lockstep with migration 218
- PostgREST OpenAPI re-enable in production vs CI-only scrape (currently `PGRST_OPENAPI_MODE: disabled`)
- `carbon-5` consumer's stale `bronze, silver, gold` allowed_schemas — ask the carbon-5 owner

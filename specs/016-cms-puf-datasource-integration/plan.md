# Implementation Plan: CMS PUF Data Source Integration

**Branch**: `016-cms-puf-datasource-integration` | **Date**: 2026-03-01 | **Revised**: 2026-03-11
**Input**: [spec.md](./spec.md) | **Canon**: dk-canon CANON.md v2026-03-11

---

## 1. Technical Context

### Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Database | PostgreSQL 16.4 (CloudNativePG) |
| Transforms | SQLMesh ≥0.90 |
| API | PostgREST v12.2.3 + FastAPI (job-trigger) |
| LLM | LiteLLM proxy (OpenAI-compatible client, Haiku alias) |
| Async | Kubernetes Jobs + CronJobs |
| Secrets | Doppler (`dk-data-fe` project) |
| Observability | OpenTelemetry + structlog |
| CI/CD | GitHub Actions → GHCR → ArgoCD |

### Key Decisions (from canon audit)

| Decision | Rationale |
|----------|-----------|
| K8s Jobs (not BullMQ) | dk-data-FE is Python-only, no Node.js runtime |
| LiteLLM (not direct Anthropic SDK) | Canon mandates LiteLLM for all LLM calls |
| Existing schemas (not new CMS-prefixed) | Avoid schema proliferation; `cms_` table prefix suffices |
| All 6 agents kept | Each solves a genuinely non-SQL problem |
| PostgREST only (no MCP tools) | Consumers own cold-start fallback; dk-data-FE = fetch/transform/expose |
| 8 phases (not 15) | Compressed for manageability |

---

## 2. Phases

### Phase 1: Foundation (weeks 1–3)

**Goal**: Database migrations, base infrastructure, LiteLLM integration.

**Deliverables**:
- [ ] Migration `083_cms_raw_tables.sql` — 30 raw tables with partitioning
- [ ] Migration `084_cms_bronze_seeds.sql` — SQLMesh model registration
- [ ] Migration `085_cms_silver_tables.sql` — agent output target tables
- [ ] Migration `086_cms_gold_views.sql` — 5 materialized views
- [ ] Migration `087_cms_agent_tables.sql` — execution log + quarantine
- [ ] Migration `088_cms_api_views.sql` — API views + permissions
- [ ] db-init-job.yaml extended (new views, permissions, verification count)
- [ ] PostgREST configmap updated (`gold` in `PGRST_DB_SCHEMAS`)
- [ ] Doppler secrets added (`LITELLM_BASE_URL`, `LITELLM_API_KEY`)
- [ ] `BaseAgent` class with LiteLLM client, execution logging, quarantine
- [ ] `BaseFetcher` extended for generic params (`npi`, `ccn`, `params`)
- [ ] Remove MCP routes from `src/dk_data/api/routes/mcp/`

**Files**:
```
src/dk_data/sql/migrations/083_cms_raw_tables.sql
src/dk_data/sql/migrations/084_cms_bronze_seeds.sql
src/dk_data/sql/migrations/085_cms_silver_tables.sql
src/dk_data/sql/migrations/086_cms_gold_views.sql
src/dk_data/sql/migrations/087_cms_agent_tables.sql
src/dk_data/sql/migrations/088_cms_api_views.sql
src/dk_data/agents/__init__.py
src/dk_data/agents/base_agent.py
k8s/base/db-init-job.yaml (extend)
k8s/base/postgrest/configmap.yaml (extend)
```

### Phase 2: Provider MVP (weeks 4–7)

**Goal**: 7 provider sources ingested, bronze/silver/gold pipeline working end-to-end.

**Deliverables**:
- [ ] 7 fetchers: NPPES, Part D Prescriber, Physician PUF, Open Payments (3), Care Compare
- [ ] 7 Pydantic source loaders
- [ ] 7 SQLMesh bronze models
- [ ] SQLMesh silver models: `cms_provider_profile` (joins NPI + prescribing + procedures + payments)
- [ ] SQLMesh gold model: `cms_provider_360`
- [ ] 7 K8s CronJob manifests
- [ ] Source registry entries in `main.py`
- [ ] Integration test: fetch → ingest → transform → PostgREST query

**Files**:
```
src/dk_data/ingestion/fetchers/cms_nppes.py
src/dk_data/ingestion/fetchers/cms_part_d_prescriber.py
src/dk_data/ingestion/fetchers/cms_physician_puf.py
src/dk_data/ingestion/fetchers/cms_open_payments.py
src/dk_data/ingestion/fetchers/cms_care_compare.py
src/dk_data/ingestion/sources/cms_nppes.py
src/dk_data/ingestion/sources/cms_part_d_prescriber.py
src/dk_data/ingestion/sources/cms_physician_puf.py
src/dk_data/ingestion/sources/cms_open_payments.py
src/dk_data/ingestion/sources/cms_care_compare.py
src/dk_data/sqlmesh/models/cms/bronze/*.sql (7 models)
src/dk_data/sqlmesh/models/cms/silver/cms_provider_profile.sql
src/dk_data/sqlmesh/models/cms/gold/cms_provider_360.sql
k8s/base/ingestion/cronjob-fetch-cms-nppes.yaml (+ 6 more)
```

### Phase 3: Facility MVP (weeks 8–11)

**Goal**: 10 facility sources, facility gold view working.

**Deliverables**:
- [ ] 10 fetchers + loaders
- [ ] 10 SQLMesh bronze models
- [ ] SQLMesh silver models: `cms_facility_profile`
- [ ] SQLMesh gold model: `cms_facility_360`
- [ ] 10 K8s CronJob manifests
- [ ] Schema evolution: `healthcare_facilities` PK migration (§E)

**Files**: Same pattern as Phase 2 in `cms/` subdirectories.

### Phase 4: Drug/Market MVP (weeks 12–15)

**Goal**: 13 drug/market/population sources, remaining gold views.

**Deliverables**:
- [ ] 13 fetchers + loaders
- [ ] 13 SQLMesh bronze models
- [ ] SQLMesh silver + gold models for drug market, market analytics
- [ ] 13 K8s CronJob manifests

### Phase 5: Agent Enrichment (weeks 16–19)

**Goal**: All 6 Silver+ agents operational.

**Deliverables**:
- [ ] `ServiceLineInference` agent + K8s Job manifest
- [ ] `IDNHierarchy` agent + K8s Job manifest
- [ ] `ReferralNetwork` agent + K8s Job manifest
- [ ] `ContactVerification` agent + K8s Job manifest
- [ ] `StaffingDecomposition` agent + K8s Job manifest
- [ ] `EquipmentInventoryInference` agent + K8s Job manifest
- [ ] Agent trigger endpoint in FastAPI job-trigger service
- [ ] Monthly CronJob for agent orchestration
- [ ] Quarantine review API endpoint

**Files**:
```
src/dk_data/agents/service_line_inference.py
src/dk_data/agents/idn_hierarchy.py
src/dk_data/agents/referral_network.py
src/dk_data/agents/contact_verification.py
src/dk_data/agents/staffing_decomposition.py
src/dk_data/agents/equipment_inventory.py
k8s/base/ingestion/cronjob-agents-monthly.yaml
```

### Phase 6: Gold Views & API (weeks 20–22)

**Goal**: All 5 PostgREST gold views materialized and queryable.

**Deliverables**:
- [ ] `gold.cms_provider_profile` — complete with agent-enriched fields
- [ ] `gold.cms_facility_profile` — complete with agent-enriched fields
- [ ] `gold.cms_drug_market_profile`
- [ ] `gold.cms_market_analytics`
- [ ] `gold.cms_provider_network`
- [ ] Materialized view refresh schedule (CronJob)
- [ ] PostgREST integration test suite

### Phase 7: Pipeline Automation (weeks 23–25)

**Goal**: Automated refresh, monitoring, alerting.

**Deliverables**:
- [ ] `meta.refresh_log` entries for all 30 CMS sources
- [ ] Staleness detection (alert if source >2× expected frequency without refresh)
- [ ] SQLMesh DAG validation (no orphaned models)
- [ ] `meta.data_sources` catalog entries for all 54 sources
- [ ] Grafana dashboard for CMS pipeline health

### Phase 8: Polish & Hardening (weeks 26–27)

**Goal**: Production readiness.

**Deliverables**:
- [ ] All verification commands pass (spec §11)
- [ ] Canon feature branch checklist passes
- [ ] Load test: NPPES 8GB ingest under 2 hours
- [ ] Agent cost validation: monthly spend within $175–385 budget
- [ ] Documentation updated in quickstart.md

---

## 3. Dependency Graph

```
Phase 1 (Foundation)
    ↓
Phase 2 (Provider) ─────→ Phase 5 (Agents — needs bronze tables)
    ↓                         ↓
Phase 3 (Facility) ─────→ Phase 6 (Gold Views — needs silver + agent outputs)
    ↓                         ↓
Phase 4 (Drug/Market) ──→ Phase 7 (Automation)
                              ↓
                          Phase 8 (Polish)
```

**Parallel opportunities**:
- Phases 2, 3, 4 can overlap (independent source groups)
- Phase 5 agents can start once their input bronze tables exist
- Phase 6 gold views can start per-domain as silver models land

---

## 4. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| NPPES 8GB CSV causes OOM | Ingestion fails | Streaming chunked reads in BaseFetcher (existing pattern) |
| CMS API rate limits | Slow ingestion | Exponential backoff in urllib3 retry (existing), prefer bulk CSV over API |
| LiteLLM proxy unreachable | Agent jobs fail | K8s `backoffLimit: 3`, alert on 3 consecutive failures |
| Agent cost overrun | Budget exceeded | Cap batch sizes, monitor `meta.agent_execution_log.cost_usd` |
| Schema migration breaks existing tables | Data loss | Migrations are additive only (CREATE, not ALTER/DROP existing) |
| PostgREST doesn't expose new gold views | API returns nothing | Verify `PGRST_DB_SCHEMAS` includes `gold` in Phase 1 |
| Partitioning increases query complexity | Slow queries | Ensure partition keys (`year`) appear in WHERE clauses |

---

## 5. Key Files Reference

| Purpose | Path |
|---------|------|
| Fetcher base class | `src/dk_data/ingestion/fetchers/base.py` |
| Source registry | `src/dk_data/ingestion/main.py` |
| SQLMesh config | `src/dk_data/sqlmesh/config.yaml` |
| SQLMesh models | `src/dk_data/sqlmesh/models/cms/` |
| Agent base class | `src/dk_data/agents/base_agent.py` |
| Agent implementations | `src/dk_data/agents/*.py` |
| K8s CronJobs | `k8s/base/ingestion/cronjob-fetch-cms-*.yaml` |
| db-init-job | `k8s/base/db-init-job.yaml` |
| PostgREST config | `k8s/base/postgrest/configmap.yaml` |
| Migrations | `src/dk_data/sql/migrations/083-088_*.sql` |
| Tests | `tests/test_cms_*.py` |

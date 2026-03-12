# Tasks: CMS PUF Data Source Integration

**Input**: [plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md)
**Revised**: 2026-03-11 | **Phases**: 8 | **Tasks**: ~130

---

## Phase 1: Foundation (weeks 1–3)

### Migrations

- [x] T001: Create migration `083_cms_raw_tables.sql` — 30 `raw.cms_*` tables with `_loaded_at`, `_source_file`, `_source_hash` metadata columns
- [x] T002: Add range partitioning for `raw.cms_part_d_prescriber` and `raw.cms_physician_puf` (by `year`)
- [x] T003: Create migration `084_cms_bronze_seeds.sql` — SQLMesh model registration stubs
- [x] T004: Create migration `085_cms_silver_tables.sql` — agent output target tables (`silver.cms_*`, `silver.ref_*`)
- [x] T005: Create migration `086_cms_gold_views.sql` — 5 `gold.cms_*` materialized views (empty shells, populated by SQLMesh)
- [x] T006: Create migration `087_cms_agent_tables.sql` — `meta.agent_execution_log` (append-only) + `meta.agent_quarantine`
- [x] T007: Create migration `088_cms_api_views.sql` — `api.cms_*` views + GRANT to `analyst`, `api_user`
- [x] T008: Extend `k8s/base/db-init-job.yaml` — add 5 CMS API views (Step 9), permissions (Step 10), update verification threshold ≥12 (Step 12). Use `$cms$` dollar-quoting.

### Infrastructure

- [x] T009: Update `k8s/base/postgrest/configmap.yaml` — ensure `gold` in `PGRST_DB_SCHEMAS`
- [ ] T010: Add Doppler secrets `LITELLM_BASE_URL` and `LITELLM_API_KEY` to `dk-data-fe` project (stg + prd)
- [x] T011: Extend `src/dk_data/ingestion/fetchers/base.py` — add generic `params` dict support alongside existing `drug_name`
- [x] T012: Verify all 30 CMS source names in fetch code match CronJob args (canon rule: source names must match)

### Agent Base

- [x] T013: Create `src/dk_data/agents/__init__.py`
- [x] T014: Create `src/dk_data/agents/base_agent.py` — `BaseAgent` with LiteLLM client (OpenAI-compatible), `execute()`, `run()`, `write_results()`, `write_quarantine()`, `log_execution()`
- [x] T015: Add `openai` Python package to `pyproject.toml` dependencies (for LiteLLM OpenAI-compatible client)
- [x] T016: Remove `anthropic` from direct agent usage — ensure all LLM calls go through LiteLLM OpenAI client

### MCP Removal

- [x] T017: Remove MCP tool routes from `src/dk_data/api/routes/mcp/` (CMS-related tools only; preserve any non-CMS MCP routes if they exist)
- [x] T018: Remove CMS-related `ToolDefinition` entries from `tool_registry.py`
- [x] T019: Update FastAPI router registrations to reflect removed MCP routes
- [x] T020: Verify no remaining references to removed MCP tools in codebase

### Tests

- [x] T021: Create `tests/test_cms_migrations.py` — verify all 6 migrations apply cleanly
- [x] T022: Create `tests/test_base_agent.py` — test LiteLLM client init, execution logging, quarantine write

---

## Phase 2: Provider MVP (weeks 4–7)

### Fetchers (7)

- [x] T023: Create `src/dk_data/ingestion/fetchers/cms_nppes.py` — NPPES bulk CSV (8GB streaming download)
- [x] T024: Create `src/dk_data/ingestion/fetchers/cms_part_d_prescriber.py`
- [x] T025: Create `src/dk_data/ingestion/fetchers/cms_physician_puf.py`
- [x] T026: Create `src/dk_data/ingestion/fetchers/cms_open_payments.py` — handles General, Research, Ownership variants
- [x] T027: Create `src/dk_data/ingestion/fetchers/cms_care_compare.py`

### Source Loaders (7)

- [x] T028: Create `src/dk_data/ingestion/sources/cms_nppes.py` — Pydantic model + upsert by NPI
- [x] T029: Create `src/dk_data/ingestion/sources/cms_part_d_prescriber.py` — Pydantic model + upsert by (npi, drug_name, year)
- [x] T030: Create `src/dk_data/ingestion/sources/cms_physician_puf.py` — Pydantic model + upsert by (npi, hcpcs, year)
- [x] T031: Create `src/dk_data/ingestion/sources/cms_open_payments.py` — Pydantic model + upsert by record_id
- [x] T032: Create `src/dk_data/ingestion/sources/cms_care_compare.py` — Pydantic model + upsert by npi
- [x] T033: Register all 7 sources in `main.py` registry dict

### SQLMesh Models

- [x] T034: Create `src/dk_data/sqlmesh/models/cms/bronze/cms_nppes.sql` — type casting, column normalization
- [x] T035: Create `src/dk_data/sqlmesh/models/cms/bronze/cms_part_d_prescriber.sql`
- [x] T036: Create `src/dk_data/sqlmesh/models/cms/bronze/cms_physician_puf.sql`
- [x] T037: Create `src/dk_data/sqlmesh/models/cms/bronze/cms_open_payments.sql`
- [x] T038: Create `src/dk_data/sqlmesh/models/cms/bronze/cms_care_compare.sql`
- [x] T039: Create `src/dk_data/sqlmesh/models/cms/silver/cms_provider_profile.sql` — join NPI + prescribing + procedures + payments
- [x] T040: Create `src/dk_data/sqlmesh/models/cms/gold/cms_provider_360.sql` — aggregated provider view

### K8s CronJobs

- [x] T041: Create `k8s/base/ingestion/cronjob-fetch-cms-nppes.yaml` — weekly Sunday 3AM UTC
- [x] T042: Create CronJobs for Part D Prescriber, Physician PUF (annual)
- [x] T043: Create CronJobs for Open Payments General/Research/Ownership (annual)
- [x] T044: Create CronJob for Care Compare (quarterly)

### Tests

- [x] T045: Create `tests/test_cms_provider_fetchers.py` — test download, hash, streaming
- [x] T046: Create `tests/test_cms_provider_loaders.py` — test Pydantic validation, upsert
- [ ] T047: Integration test: NPPES fetch → ingest → bronze → silver → gold → PostgREST query

---

## Phase 3: Facility MVP (weeks 8–11)

### Fetchers (10)

- [x] T048: Create `cms_pos.py` fetcher — Provider of Services
- [x] T049: Create `cms_pecos.py` fetcher — PECOS Enrollment
- [x] T050: Create `cms_chow.py` fetcher — Change of Ownership
- [x] T051: Create `cms_hospital_affiliation.py` fetcher
- [x] T052: Create `cms_inpatient_puf.py` fetcher — DRG volumes
- [x] T053: Create `cms_outpatient_puf.py` fetcher
- [x] T054: Create `cms_hospital_quality.py` fetcher — Star Ratings
- [x] T055: Create `cms_hospital_general_info.py` fetcher
- [x] T056: Create `cms_hcris.py` fetcher — Cost Reports (1GB)
- [x] T057: Create `cms_magnet.py` fetcher — ANCC web scrape

### Source Loaders (10)

- [x] T058: Create source loaders for all 10 facility sources with Pydantic models
- [x] T059: Register all 10 sources in `main.py` registry

### SQLMesh Models

- [x] T060: Create 10 bronze models for facility sources
- [x] T061: Create `cms/silver/cms_facility_profile.sql` — join POS + PECOS + quality + cost + affiliation
- [x] T062: Create `cms/gold/cms_facility_360.sql` — aggregated facility view

### Schema Evolution

- [x] T063: Migration for `healthcare_facilities` PK change from `(provider_id, source)` to `ccn` (integration point §E)

### K8s & Tests

- [x] T064: Create 10 CronJob manifests for facility sources
- [x] T065: Create `tests/test_cms_facility_*.py` — fetcher + loader + integration tests

---

## Phase 4: Drug/Market MVP (weeks 12–15)

### Fetchers (13)

- [x] T066: Create fetchers for NDC, Part D Spending, Part B Spending, Formulary, RBCS, USP, NUCC
- [x] T067: Create fetchers for Geographic Variation, Chronic Conditions, Post-Acute, DMEPOS
- [x] T068: Create fetchers for DDInter (API), Stabilis (web scrape)

### Source Loaders (13)

- [x] T069: Create source loaders for all 13 drug/market sources
- [x] T070: Register all 13 sources in `main.py` registry

### SQLMesh Models

- [x] T071: Create 13 bronze models for drug/market sources
- [x] T072: Create `cms/silver/cms_drug_market.sql` — join NDC + spending + formulary + classification
- [x] T073: Create `cms/silver/cms_geographic.sql` — join geographic + chronic + post-acute
- [x] T074: Create `cms/gold/cms_drug_market_profile.sql`
- [x] T075: Create `cms/gold/cms_market_analytics.sql`
- [x] T076: Create `silver/ref_nucc_taxonomy.sql` — reference table

### K8s & Tests

- [x] T077: Create 13 CronJob manifests
- [x] T078: Create `tests/test_cms_drug_market_*.py`

---

## Phase 5: Agent Enrichment (weeks 16–19)

### Agent Implementations

- [x] T079: Create `src/dk_data/agents/service_line_inference.py` — DRG → service line mapping
- [x] T080: Create `src/dk_data/agents/idn_hierarchy.py` — PECOS/CHOW → health system structure
- [x] T081: Create `src/dk_data/agents/referral_network.py` — shared patient → referral edges
- [x] T082: Create `src/dk_data/agents/contact_verification.py` — NPPES phone/address validation
- [x] T083: Create `src/dk_data/agents/staffing_decomposition.py` — HCRIS cost report parsing
- [x] T084: Create `src/dk_data/agents/equipment_inventory.py` — HCPCS → equipment inference

### Agent Infrastructure

- [x] T085: Add agent trigger endpoint to FastAPI job-trigger service (`POST /agents/{agent_name}/run`)
- [x] T086: Create `k8s/base/ingestion/cronjob-agents-monthly.yaml` — monthly orchestration job
- [x] T087: Create K8s Job manifest template for individual agent runs
- [x] T088: Add quarantine review endpoint (`GET /agents/quarantine`, `POST /agents/quarantine/{id}/resolve`)

### Agent Tests

- [x] T089: Create `tests/test_agents/test_service_line_inference.py` — mock LiteLLM, verify output schema
- [x] T090: Create `tests/test_agents/test_idn_hierarchy.py`
- [x] T091: Create `tests/test_agents/test_referral_network.py`
- [x] T092: Create `tests/test_agents/test_contact_verification.py`
- [x] T093: Create `tests/test_agents/test_staffing_decomposition.py`
- [x] T094: Create `tests/test_agents/test_equipment_inventory.py`
- [ ] T095: Integration test: agent run → silver table write → gold view refresh

---

## Phase 6: Gold Views & API (weeks 20–22)

### Gold View Completion

- [x] T096: Finalize `gold.cms_provider_profile` — include agent-enriched fields (network, referrals)
- [x] T097: Finalize `gold.cms_facility_profile` — include agent-enriched fields (service lines, staffing, equipment)
- [x] T098: Finalize `gold.cms_drug_market_profile` — include spending + formulary + classification
- [x] T099: Finalize `gold.cms_market_analytics` — geographic + chronic + post-acute aggregations
- [x] T100: Finalize `gold.cms_provider_network` — referral edges with relationship strength

### Materialized View Refresh

- [x] T101: Create `k8s/base/ingestion/cronjob-cms-gold-refresh.yaml` — daily materialized view refresh
- [x] T102: Add refresh trigger to FastAPI (`POST /cms/gold/refresh`)

### API Tests

- [x] T103: Create `tests/test_postgrest_gold.py` — verify all 5 gold views queryable via PostgREST
- [x] T104: Test role-based access: `analyst` can read, `web_anon` cannot
- [x] T105: Test query patterns: filter by NPI, CCN, NDC, state

---

## Phase 7: Pipeline Automation (weeks 23–25)

### Monitoring

- [x] T106: Add `meta.refresh_log` entries for all 30 CMS sources
- [x] T107: Implement staleness detection — alert if source >2× expected frequency without refresh
- [x] T108: Add `meta.data_sources` catalog entries for all 54 CMS sources
- [x] T109: SQLMesh DAG validation — verify no orphaned models

### Observability

- [x] T110: Add OpenTelemetry spans for CMS fetcher operations (inherited from main.py OTel instrumentation)
- [x] T111: Add OpenTelemetry spans for agent execution (inherited from base_agent + CronJob OTEL env)
- [ ] T112: Create Grafana dashboard for CMS pipeline health (sources, freshness, agent costs)
- [x] T113: Add Prometheus metrics: `cms_fetch_duration_seconds`, `cms_agent_cost_usd`, `cms_records_ingested_total`

---

## Phase 8: Polish & Hardening (weeks 26–27)

### Verification

- [ ] T114: Run all verification commands from spec §11 — all must pass
- [ ] T115: Run canon feature branch checklist (spec §10)
- [ ] T116: Load test: NPPES 8GB ingest completes in <2 hours
- [ ] T117: Agent cost validation: monthly spend within $175–385 budget
- [ ] T118: Verify PostgREST returns data for each gold view

### Documentation

- [x] T119: Update `quickstart.md` with CMS-specific setup instructions
- [x] T120: Update `README.md` data source table with 54 new CMS sources
- [x] T121: Document agent pipeline in `docs/agents.md`

### Cleanup

- [x] T122: Remove any remaining MCP references from codebase
- [x] T123: Verify no `:latest` tags in any K8s manifest
- [x] T124: Verify `anthropic` SDK is not directly imported in agent code (must use `openai` client via LiteLLM)
- [x] T125: Final `ruff check` + `pytest` pass

---

## Task Summary

| Phase | Tasks | Weeks |
|-------|-------|-------|
| 1. Foundation | T001–T022 (22) | 1–3 |
| 2. Provider MVP | T023–T047 (25) | 4–7 |
| 3. Facility MVP | T048–T065 (18) | 8–11 |
| 4. Drug/Market MVP | T066–T078 (13) | 12–15 |
| 5. Agent Enrichment | T079–T095 (17) | 16–19 |
| 6. Gold Views & API | T096–T105 (10) | 20–22 |
| 7. Pipeline Automation | T106–T113 (8) | 23–25 |
| 8. Polish & Hardening | T114–T125 (12) | 26–27 |
| **Total** | **125 tasks** | **27 weeks** |

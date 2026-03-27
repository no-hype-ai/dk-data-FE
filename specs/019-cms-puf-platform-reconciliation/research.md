# Research: CMS PUF & Platform Data Reconciliation

**Phase**: 0 — Research
**Feature**: `019-cms-puf-platform-reconciliation`
**Date**: 2026-03-27

---

## 1. BaseFetcher Retry Logic — Already Implemented

**Decision**: FR-016a (retry-with-backoff in BaseFetcher) is substantially already satisfied on main.

**Finding**: `src/dk_data/ingestion/fetchers/base.py` constructs a `requests.Session` with:

```python
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
```

This gives all subclasses automatic retry-with-exponential-backoff (delays: 0s, 1s, 2s) on `429` and server errors. No per-fetcher changes needed.

**Delta required**: The spec clarification asked for per-source configurable `max_retries` / `retry_base_delay_seconds` in the `SOURCES` dict. Since `BaseFetcher.__init__` builds the `Retry` object with hardcoded values, per-source config would require a small extension: read `max_retries` / `retry_base_delay_seconds` from `SOURCES` config and pass to `Retry` in the session setup. Estimated: ~15 lines in `main.py` + no changes to individual fetchers.

**Rationale**: Centralised in `BaseFetcher` (as clarified); per-source config read from `SOURCES` entry at `run_ingestion()` time and injected via constructor kwarg or session reconfiguration.

**Alternatives considered**: Per-fetcher implementation — rejected (duplication across 28+ fetchers); no retry (rejected by clarification Q3).

---

## 2. trial_outcomes.sql — References xenon on Main

**Decision**: `mol_gold.trial_outcomes` must be updated to remove the `xenon.publication_evidence` reference and replace it with `mol_silver.publication_evidence`.

**Finding**: `src/dk_data/sqlmesh/models/molecules/gold/trial_outcomes.sql` on main already exists and contains:

```sql
FROM xenon.publication_evidence pe
WHERE pe.confidence_score >= 0.40
```

This is the exact dependency FR-024a and FR-033 require us to eliminate. The file is **not** marked `.removed` on main — it exists and is active. The 016 branch had removed it; main restored a version that still references xenon.

**Delta required**: Update `trial_outcomes.sql` to JOIN against `mol_silver.publication_evidence` instead of `xenon.publication_evidence`. The table `mol_silver.publication_evidence` does not yet exist on main — it is created by the consolidated migration.

**Grain correction**: Main `trial_outcomes.sql` uses `grain (molecule_id, trial_nct_id, evidence_source)`. The spec defines `grain (molecule_id, trial_nct_id, endpoint_name, evidence_source)`. The more granular grain is correct — one trial can have multiple endpoints; using `endpoint_name` as part of the grain prevents collapsing endpoints into a single row.

**Rationale**: Adding `endpoint_name` to the grain is a non-breaking change (more rows, not fewer). Removing xenon dependency is the primary correctness goal.

---

## 3. SOURCES Dict — File-Based Sources Have No `fetcher` Key

**Decision**: The spec's Canonical Ingestion Patterns section is correct; however, the code shows that file-based sources in the actual `SOURCES` dict do **not** include a `fetcher` key.

**Finding**: In `src/dk_data/ingestion/main.py`:
- File-based sources (`requires_file: True`): keys are `name`, `description`, `loader`, `requires_file`, optionally `meta_name`, `requires_fiscal_year`
- API sources (`requires_file: False`): add `fetcher` and `default_days_back`

The 28 CMS PUF sources are file-based. Their SOURCES entries will **not** have a `fetcher` key. The file download happens externally (CronJob downloads to a mounted volume; loader is called with the file path).

**Rationale**: CMS PUF files are bulk annual releases (not streamed APIs). The file acquisition is a separate operational step from the SQL load. Keeping them separate preserves the existing architecture.

**Impact on spec**: The Canonical Ingestion Patterns code example showing both `fetcher`-bearing and file-only entries is correct as written. No spec change needed.

---

## 4. Migration Number — Next Is 085

**Decision**: The consolidated migration script will be `085_cms_puf_platform_reconciliation.sql`.

**Finding**: The latest migration on main is `084_add_response_hash_columns.sql`. All prior 016 migrations (001–057 in the 016 branch numbering) must be audited against current main schema. Only the delta — schemas, tables, and columns that do not yet exist on main — goes into 085.

**Rationale**: Single consolidated migration per FR-020. The 016 branch had 57 migrations; many reference dropped schemas or columns that no longer apply (per FR-021). A fresh delta-only migration avoids replay failures.

**Key new objects in 085**:
- `hcs_raw` schema + 7 CMS raw tables (if not created by 084 or earlier)
- `hcs_bronze` schema + bronze models (managed by SQLMesh, not migration — schema creation only)
- `hcs_silver`, `hcs_gold` schemas
- `mol_silver.publication_evidence` table
- `mol_silver.physician_payments` table (if not on main)
- `mol_silver.research_grants` table (if not on main)
- Agent quarantine table: `mol_silver.agent_quarantine`
- `meta.data_sources` INSERT rows for all 28 new CMS sources + 6 new API sources

---

## 5. PostgREST Schema Exposure — Config Location

**Decision**: The PostgREST `db-schemas` config is set via a Doppler-managed environment variable injected into the PostgREST deployment; schema additions require a Doppler project update and a PostgREST pod restart.

**Finding**: PostgREST is deployed as a K8s service. Schema exposure is controlled by `PGRST_DB_SCHEMAS` env var (comma-separated list). Current exposure includes `mol_bronze`, `mol_silver`, `mol_gold` and HCS equivalents will be added in this PR.

**Delta required**: Add `hcs_bronze`, `hcs_silver`, `hcs_gold` (and any `ind_` prefixed schemas when introduced) to `PGRST_DB_SCHEMAS`. Update PostgREST K8s manifest or Doppler config. Raw schemas (`mol_raw`, `hcs_raw`) must never appear in this list.

---

## 6. Grafana Alert Delivery — monitoring/provisioning

**Decision**: The pipeline failure alert rule (FR-034) should be provisioned via `monitoring/provisioning/` using Grafana's provisioning file format.

**Finding**: `monitoring/provisioning/grafana-data-platform.yaml` exists. Grafana alerts can be provisioned alongside dashboards. The alert rule queries `meta.refresh_log` for N consecutive failures using a PostgreSQL datasource query.

**Delta required**: Add `monitoring/provisioning/alerts/pipeline-source-failures.yaml` with a Grafana alert group. The alert fires when `COUNT(*) FILTER (WHERE status = 'failed') >= 3` for any `source_id` in the last N most-recent rows of `meta.refresh_log`.

---

## 7. Agent System — Existing `agents/` Directory Is Empty

**Finding**: `src/dk_data/agents/` exists but contains only `__pycache__`. The 7 agents from the 016 branch were never ported. All 7 agent files must be written from scratch in this PR, following the LiteLLM proxy routing pattern and the BaseFetcher-parallel pattern for agent base classes.

**Agent inventory** (FR-024):
1. `service_line_inference.py` — DRG claims → clinical service line assignments
2. `idn_hierarchy.py` — facility grouping → IDN parent-child relationships
3. `referral_network.py` — claims patterns → referral flow graph
4. `contact_verification.py` — NPI records → verified contact attributes
5. `staffing_decomposition.py` — cost report staffing → role decomposition
6. `equipment_inventory.py` — claims codes → implied equipment inventory
7. `publication_evidence_extractor.py` — publication abstracts → structured clinical endpoints → `mol_silver.publication_evidence`

---

## 8. SQLMesh Model Paths — HCS Models Need New Directory

**Finding**: Current SQLMesh model tree:
```
src/dk_data/sqlmesh/models/molecules/{bronze,silver,gold}/
```

There is no `hcs/` directory. New HCS models need:
```
src/dk_data/sqlmesh/models/hcs/{bronze,silver,gold}/
```

SQLMesh discovers models by scanning `models/` recursively, so subdirectory structure is arbitrary — the `MODEL(name hcs_bronze.cms_part_d_spending)` declaration in the file controls the schema, not the directory path. Convention aligns directory name with schema namespace.

---

## 9. Existing Bronze Models to Leverage or Extend

**Finding**: Several relevant bronze models already exist on main:
- `molecules/bronze/ema.sql` — EMA regulatory; needs review to confirm it maps to `mol_bronze.ema_regulatory` namespace
- `molecules/bronze/cochrane_reviews.sql` — already ingesting Cochrane
- `molecules/bronze/drugbank.sql` — already exists
- `molecules/bronze/sec_edgar.sql` — already exists

**Delta**: CMS PUF sources are new (no existing bronze). EuropePMC and NIH Reporter are new. Existing bronze models may need namespace alignment checks (e.g., `ema.sql` may declare `name molecules.ema` rather than `mol_bronze.ema_regulatory`).

---

## 10. LiteLLM Integration — Agent Call Pattern

**Decision**: All LLM calls in new agents MUST use the LiteLLM proxy via the OpenAI-compatible endpoint. The `anthropic` Python SDK MUST NOT be imported in any new agent or loader file introduced by this feature.

**Finding**: Three existing files (`claude_sdk/enrichment.py`, `claude_sdk/scoring_agent.py`, `iva_evidence_report_workflow.py`) import `anthropic` directly — this is a pre-existing CANON violation in `claude_sdk/`. New agents introduced by this feature must not extend this pattern.

**LiteLLM proxy address**:
- K8s (prod/staging): `http://litellm.infra.svc.cluster.local:8000/v1`
- Bare-metal / local dev: `http://192.168.10.50:4000/v1`
- Env var: `LITELLM_PROXY_URL` (Doppler-sourced, project `dk-data-fe`)

**Model aliases** (use these strings only — never hardcode provider model IDs):
- `pharma-llm` — local/cheap model (first attempt)
- `claude-sonnet-4-20250514` — frontier model (escalation)
- `gpt-4o-mini` — lightweight classification

**Shared rate limit**: 500 RPM across all DataKinetic services. Agents MUST implement exponential backoff on `429` responses. With 7 agents potentially running simultaneously, each agent should pace its LLM calls (max 5 concurrent per agent run) and use `tenacity` for retry logic on the LiteLLM call layer.

**Call pattern** (using `openai` SDK pointed at LiteLLM):
```python
from openai import OpenAI
import os

client = OpenAI(
    base_url=os.environ["LITELLM_PROXY_URL"],
    api_key=os.environ["LITELLM_API_KEY"],   # LiteLLM virtual key from Doppler
)
```

**Quality escalation** (ARCHITECTURE-BEST-PRACTICES.md mandate): Call `pharma-llm` first; if confidence score < 0.6, re-call with `claude-sonnet-4-20250514`. One escalation maximum per record.

**Tenacity vs urllib3.Retry**: `urllib3.Retry` is for HTTP fetchers (BaseFetcher already uses it for downstream data source calls). `tenacity` is for LLM call retry in agents (handles `RateLimitError`, `APIStatusError` 429 from LiteLLM). These are separate retry layers with no overlap.

**Rationale**: CANON mandates "Never call OpenAI/Anthropic directly; use LiteLLM virtual key via Doppler." All 7 new agents must comply. The openai SDK pointing at LiteLLM is the canonical Python pattern for dk-data-FE.

**Alternatives considered**: Anthropic SDK with proxy URL — rejected (CANON violation, wrong client library); direct httpx calls — acceptable but openai SDK provides better error types for 429 handling.

---

## Summary of Research Decisions

| Topic | Decision | Action Required |
|---|---|---|
| BaseFetcher retry | Already implemented; extend for per-source config | ~15 lines in main.py |
| trial_outcomes.sql | Exists on main, references xenon — update required | Edit SQL file, fix grain |
| SOURCES file-based | No `fetcher` key for file-based sources | Correct — no spec change needed |
| Migration number | Next migration is 085 | Write 085_cms_puf_platform_reconciliation.sql |
| PostgREST config | Doppler env var — add hcs_silver/hcs_gold only | Update configmap.yaml (hcs_bronze excluded) |
| Grafana alert | Provisioning file at monitoring/provisioning/alerts/ | New YAML file |
| Agents directory | Empty on main — all 7 agents must be written | 7 new Python files |
| HCS SQLMesh path | New hcs/ subdirectory needed | Create directory tree |
| Existing bronze | EMA/Cochrane/DrugBank/EDGAR already exist | Verify namespace alignment |
| Schema naming split | bronze (legacy), mol_bronze (mol-CI), hcs_bronze (new) | All three via config.yaml mappings |
| silver.publications | Existing model — EuropePMC extends as 5th CTE | No new mol_silver.europepmc table |
| MCP duplication | TOOL_REGISTRY + adapters/ already exist | Extend existing files, no new services/data_tools/ |
| LiteLLM agents | openai SDK → LiteLLM proxy; tenacity for retry | No import anthropic in new code; 500 RPM shared limit |

---

## 11. Migration Audit: 016-Branch vs Feature-019 Migration 085

**Date**: 2026-03-27
**Method**: Full read of all 58 NEW migrations on the 016 branch (083–140, excluding 131 which was renumbered to 140). Cross-referenced against `085_cms_puf_platform_reconciliation.sql` on the feature-019 branch.

### 11.1 Summary Table

| Migration | Description | Objects Created | Overlap with 085? | Action Needed |
|-----------|-------------|-----------------|-------------------|---------------|
| **083** `cms_raw_tables` | 30 hcs_raw.cms_* typed-column tables — providers (7), facilities (10), drugs (13). Partitioned tables for prescriber/physician PUF | `hcs_raw.cms_nppes`, `cms_part_d_prescriber` (partitioned), `cms_physician_puf` (partitioned), `cms_open_payments_general/research/ownership`, `cms_care_compare_physicians`, `cms_pos`, `cms_pecos`, `cms_chow`, `cms_hospital_affiliation`, `cms_inpatient_puf`, `cms_outpatient_puf`, `cms_hospital_quality`, `cms_hospital_general_info`, `cms_hcris`, `cms_magnet`, `cms_ndc`, `cms_part_d_spending`, `cms_part_b_spending`, `cms_formulary`, `cms_rbcs`, `cms_usp`, `cms_nucc`, `cms_geographic_variation`, `cms_chronic_conditions`, `cms_post_acute`, `cms_dmepos`, `cms_ddinter`, `cms_stabilis` | **Partial** — 085 creates hcs_raw schema + 28 of the same CMS tables but with BIGSERIAL/TEXT column schemas (not partitioned, different column names). The 016 branch used partitioned tables keyed by `year`; 085 uses non-partitioned with `_source_year INTEGER`. Names differ (e.g. 016 uses `cms_part_d_prescriber`, 085 uses `cms_part_d_spending`). Table-for-table these are **different schemas** for some overlapping sources. | 085 already covers hcs_raw schema + core CMS tables. Migration 134 on 016 branch DROPS all typed tables and replaces them with JSONB pattern — so typed tables are transient. 085 is choosing a different but equally valid approach (structured columns). No gap. |
| **084** `cms_bronze_seeds` | No-op placeholder — SQLMesh manages bronze DDL | None (SELECT 1) | No overlap | Safe to ignore — design decision noted. |
| **085** (016) `cms_silver_tables` | 8 hcs_silver tables: `cms_provider_profile`, `cms_facility_profile`, `cms_drug_market`, `cms_geographic`, `ref_drg_service_line`, `ref_hcpcs_equipment`, `ref_nucc_taxonomy`, `cms_health_system_hierarchy`, `cms_referral_edges`, `cms_verified_contacts`, `cms_staffing_profiles`, `cms_equipment_inventory`. Also creates bare `silver` schema. | `hcs_silver.*` (12 tables) | **Partial** — 085 (019) creates `hcs_silver.service_lines`, `idn_hierarchy`, `referral_network`, `verified_contacts`, `staffing_decomposition`, `equipment_inventory`. The 016 branch names are different (e.g. `cms_provider_profile` vs `service_lines`). The 016 tables are composite/denormalized; 019 tables are agent-output-per-NPI. Conceptually overlapping purpose, structurally different. | 019's agent-output tables are correct for the spec. The 016 composite tables (provider_profile, facility_profile etc.) are SQLMesh-managed silver — not needed in 085 migration. No gap in 085. |
| **086** `cms_gold_views` | 5 gold views in hcs_gold: `cms_provider_360`, `cms_facility_360`, `cms_drug_market_profile`, `cms_market_analytics`, `cms_provider_network` — thin wrappers over hcs_silver composite tables | `hcs_gold.*` (5 views) | No overlap — 085 does not create hcs_gold views | **GAP**: 085 creates `hcs_gold` schema but no views. The gold views depend on 016's composite silver tables which 085 does not create. 019 does not need these 5 composite views — they are specific to the 016 data-tools UI design. Not a gap for 019's scope. |
| **087** `cms_agent_tables` | `meta.ops_agent_execution_log` (append-only), `meta.ops_agent_quarantine` with FK. Grants for api_user/analyst. | `meta.ops_agent_execution_log`, `meta.ops_agent_quarantine` | **Partial** — 085 creates `mol_silver.agent_quarantine`. The 016 branch puts agent log/quarantine in `meta` schema (ops_ prefix). 085 puts quarantine in `mol_silver`. These serve the same purpose but in different schemas. | **GAP**: 085 has no `meta.ops_agent_execution_log`. This table is needed by any agent infrastructure. 019 should either add it to 085 or confirm that `mol_silver.agent_quarantine` is sufficient and the execution log lives elsewhere. Recommend: add `meta.ops_agent_execution_log` to 085. |
| **088** `cms_api_views` | 5 `api.*` views wrapping the 5 hcs_gold views. Grants on `gold` schema. | `api.cms_provider_profile`, `api.cms_facility_profile`, `api.cms_drug_market`, `api.cms_market_analytics`, `api.cms_provider_network` | No overlap | Safe to ignore — these api views are for 016's data-tools design, not 019's scope. |
| **089** `cms_meta_catalog` | Inserts 28 sources into `meta.ops_data_sources`. Creates `meta.cms_staleness_report` view. | `meta.cms_staleness_report` (view) | **Partial** — 085 inserts sources into `meta.data_sources` (note: different table name: `meta.data_sources` vs `meta.ops_data_sources`). | **GAP**: Table name mismatch — 085 uses `meta.data_sources`, 016 uses `meta.ops_data_sources`. Verify which table name is canonical on main. If `meta.ops_data_sources` is the live table, 085's INSERTs will fail. Also: `meta.cms_staleness_report` is a useful monitoring view not in 085. |
| **090** `cms_facility_pk_change` | Alters `silver.healthcare_facilities` (SQLMesh-managed) to use `ccn` as PK; adds backward-compat index. Guarded by IF EXISTS. | Alters `silver.healthcare_facilities` | No overlap | Safe to ignore — `silver.*` schema was dropped in migration 121. The target table no longer exists after the 016 branch runs. |
| **091** `euipo_designs_raw` | `raw.euipo_designs` table with locarno_classes GIN index | `raw.euipo_designs` | No overlap | Safe to ignore — uses legacy `raw.*` schema (dropped in 121). Feature 014-euipo, not 019 scope. |
| **092** `data_tools_gold_views` | 17 additional gold views in hcs_gold for per-source data-tools lookups: part_d_spending, part_b_spending, chow, hospital_affiliation, rbcs, nucc, usp, stabilis, ddinter, formulary, ndc, dmepos, post_acute, nppes, pos, hcris, magnet | `hcs_gold.*` (17 views) | No overlap | Safe to ignore — data-tools endpoint views, not 019 scope. |
| **093** `data_tools_api_views` | 17 `api.*` views wrapping the 092 gold views. Grants. | `api.*` (17 views) | No overlap | Safe to ignore. |
| **094** `molecule_stage_history` | `silver.molecule_stage_history` (lifecycle audit) | `silver.molecule_stage_history` | No overlap | Safe to ignore — `silver.*` schema dropped in 121. Feature 012, not 019. |
| **095** `bronze_chembl_activities` | `bronze.chembl_activities` with FK to `raw.chembl` | `bronze.chembl_activities` | No overlap | Safe to ignore — `bronze.*` dropped in 121. Feature 012. |
| **096** `revoke_webanon_protected_views` | Revokes web_anon SELECT on protected api.* views. Defensive loop. | None (grants only) | No overlap | Safe to ignore — permission hygiene, already handled in 085 section 8. |
| **097** `grant_postgrest_schema_access` | Grants USAGE/SELECT on mol_gold, mol_silver, xenon, meta to authenticator/analyst. | None (grants only) | No overlap | Safe to ignore — 085 handles hcs_silver/hcs_gold grants already. |
| **098** `ingestion_pipeline_meta` | ALTERs `meta.ops_data_sources` to add `last_content_hash`, `last_etag`, `last_modified_header`. ALTERs `meta.ops_refresh_log` to add `content_hash`, `pagination_offset`, `skipped_by_hash`. | Column additions to existing tables | No overlap | **GAP**: If `meta.ops_data_sources` and `meta.ops_refresh_log` exist on main, these columns may not exist. 085 does INSERTs into `meta.data_sources` — but if the canonical table is `meta.ops_data_sources`, see 089 note. Not in 085's scope but needed for the ingestion pipeline to function. |
| **099** `fix_raw_table_schema_mismatches` | Creates `hcs_raw.cms_care_compare` (loader target). ALTERs 8 tables (hospital_general_info, hospital_quality, ndc, nppes, nucc, part_b_spending, pos) to add loader-expected columns. ALTERs `raw.pdb`. | `hcs_raw.cms_care_compare` (new), many column additions | No overlap | Safe to ignore — fixes schema drift between 083 and actual loaders. 085 uses its own clean column definitions aligned to its own loaders. |
| **100** `fix_remaining_loader_mismatches` | Creates `hcs_raw.cms_open_payments` (unified table). ALTERs part_d_prescriber columns. Drops PKs on hospital tables. ALTERs raw.pdb. | `hcs_raw.cms_open_payments` (new) | **Partial** — 085 creates `hcs_raw.cms_open_payments` with its own schema | 085 already creates this table correctly. No gap. |
| **101** `pdb_drop_envelope_not_null` | Drops NOT NULL on `raw.pdb` envelope columns | Column constraint changes | No overlap | Safe to ignore — raw.pdb schema fix. |
| **102** `fix_ddinter_stabilis_usp_schemas` | Recreates `hcs_raw.cms_stabilis`, `cms_formulary`. Adds columns to `cms_ddinter`, `cms_usp`, `cms_chronic_conditions`. Recreates gold views for these. | Column/table reshapes | No overlap | Safe to ignore — fixes 016 schema drift. 085 creates its own clean versions. |
| **103** `fix_hospital_affiliation_magnet_schemas` | Drops and recreates `hcs_raw.cms_hospital_affiliation`, `cms_magnet` with new schemas. Recreates gold views. | Table recreations | No overlap | Safe to ignore. |
| **104** `fix_puf_pecos_dmepos_schemas` | Drops/recreates `hcs_raw.cms_dmepos`, `cms_outpatient_puf`, `cms_pecos`. Modifies `cms_inpatient_puf`, `cms_geographic_variation`, `cms_physician_puf`. Recreates gold views. | Table/column reshapes | No overlap | Safe to ignore. |
| **105** `fix_physician_puf_geov_schemas` | Adds default partition to `cms_physician_puf`. Fixes `cms_geographic_variation` PK to (state, year). | Schema fixups | No overlap | Safe to ignore. |
| **106** `fix_chronic_conditions_schema` | Makes `year` nullable on `cms_chronic_conditions`. | Column constraint | No overlap | Safe to ignore. |
| **107** `fix_formulary_schema` | Drops/recreates `hcs_raw.cms_formulary` with (formulary_id, rxcui) PK. | Table recreation | No overlap | Safe to ignore. |
| **108** `fix_usp_alignment_schema` | Drops/recreates `hcs_raw.cms_usp` with (rxcui, usp_category, usp_class) PK for USP MMG v9.0. | Table recreation | No overlap | Safe to ignore. |
| **109** `add_clinical_trials_outcomes_locations` | ALTERs `mol_silver.clinical_trials` to add locations, primary_outcomes, secondary_outcomes, acronym, eligibility_criteria, arms. Backfills from bronze. | Column additions to mol_silver.clinical_trials | No overlap with 085 | Safe to ignore for 085. Feature 003. |
| **110** `new_mol_data_sources` | 8 new `mol_silver` tables: `physician_payments`, `protein_targets`, `hta_decisions`, `physician_profiles`, `drug_spending`, `research_grants`, `pathways`, `rems_programs`. Grants. | `mol_silver.physician_payments`, `mol_silver.protein_targets`, `mol_silver.hta_decisions`, `mol_silver.physician_profiles`, `mol_silver.drug_spending`, `mol_silver.research_grants`, `mol_silver.pathways`, `mol_silver.rems_programs` | **OVERLAP** — 085 creates `mol_silver.physician_payments` and `mol_silver.research_grants` | **CRITICAL GAP**: 016 migration 110 creates `mol_silver.physician_payments` and `mol_silver.research_grants` with **different schemas** than 085. 016 uses FK to `mol_silver.molecules(molecule_id)` and includes `physician_npi`, `payment_year`, `payment_form`. 085's versions are structurally similar but column names differ slightly. Since both branches create these tables, 085 must use `IF NOT EXISTS` (it does) and the schemas must be compatible or the merge will conflict. |
| **111** `new_sources_raw_bronze` | mol_raw + mol_bronze + mol_hcs_raw tables for fda_drugsfda, reactome, kegg, nice_hta, cms_open_payments, cms_medicare, nih_reporter, npi_registry. Also mol_bronze tables for open_payments, medicare_spending, nih_grants. | `mol_raw.fda_drugsfda`, `mol_raw.reactome`, `mol_raw.kegg`, `mol_raw.nice_hta`, `mol_hcs_raw.cms_open_payments`, `mol_hcs_raw.cms_medicare`, `mol_raw.nih_reporter`, `mol_bronze.*` (many) | **Partial** — 085 creates `mol_raw.europepmc_raw` and `mol_raw.nih_reporter_raw` as standalone tables. 016 creates `mol_raw.nih_reporter` (same concept, different name). | **GAP**: 085 creates `mol_raw.europepmc_raw` (with `_raw` suffix) and `mol_raw.nih_reporter_raw`. 016 creates `mol_raw.europepmc` (migration 125) and `mol_raw.nih_reporter` (migration 111). Name collision risk if both branches run — the `_raw` suffix in 085 is non-standard vs the rest of mol_raw.* (which don't use `_raw` suffix). Recommend: rename to `mol_raw.europepmc` and `mol_raw.nih_reporter` in 085 to match mol_raw convention. |
| **112** `align_mol_bronze_with_bronze` | Adds ~60 columns to `mol_bronze.clinicaltrials`, `mol_bronze.openfda_faers`, `mol_bronze.openfda_labels`. Backfills from `bronze.clinicaltrials`. | Column additions | No overlap | Safe to ignore — bronze schema enrichment, feature 012. |
| **113** `indication_epidemiology` | `mol_raw.who_gho`, `mol_raw.ct_gov_indication_stats`, `mol_silver.indication_epidemiology`, `mol_silver.indication_revenue`, `mol_silver.icd10_indicator_mapping` (with seed data). Adds columns to `mol_silver.financial_filings`. Inserts into `ops.sync_schedules`. | 5 tables (3 new schemas) | No overlap | Safe to ignore — indication/epidemiology data, feature 003. Not 019 scope. |
| **114** `fix_medallion_column_losses` | Adds ~10 columns to mol_bronze/silver clinical_trials. Creates `mol_silver.financial_filings` IF NOT EXISTS. Deduplicates financial_filings and regulatory_milestones. | `mol_silver.financial_filings` (if not exists) | No overlap | Safe to ignore — clinical trials and financial filings enrichment. |
| **115** `fix_deduplication` | Adds `processed_to_bronze` to 5 raw IP tables. Creates 10 unique indexes on mol_silver tables to prevent duplicates. | Unique indexes | No overlap | Safe to ignore — deduplication hygiene. |
| **116** `dailymed_hta_fix` | `mol_raw.dailymed`, `mol_silver.dailymed_labels`, `mol_raw.hta_decisions`. Inserts into `ops.sync_schedules`. | 3 tables | No overlap | Safe to ignore — DailyMed + HTA, feature 003. |
| **117** `cms_puf_ontology` | Inserts 5 rows into `xenon.xenon_data_source_ontology` for CMS gold views | INSERT only (no DDL) | No overlap | Safe to ignore — xenon ontology configuration; 019 does not manage xenon. |
| **118** `schema_prefix_enforcement` | Creates schemas: `hcs_raw`, `hcs_silver`, `hcs_gold`, `ops`. Grants USAGE/SELECT. Documents the schema inventory. | Schema creation + grants | **OVERLAP** — 085 also creates `hcs_raw`, `hcs_silver`, `hcs_gold` | Both use `IF NOT EXISTS` so no conflict. But `ops` schema: 085 does not create `ops` schema — and several 016 tables (`ops.fetch_state`, `ops.sync_schedules`, `ops.transformation_config`) live there. **GAP**: If `ops` schema doesn't exist on main, 085's grant section (section 8) granting USAGE for analyst may reference a non-existent schema. |
| **119** `gold_indication_revenue_summary` | `mol_gold.indication_revenue_summary` table. Grants. | `mol_gold.indication_revenue_summary` | No overlap | Safe to ignore — indication revenue, feature 003. |
| **120** `domain_schema_separation` | Creates schemas: `ind_silver`, `ind_gold`, `hcp_silver`, `hcp_gold`. Grants authenticator/analyst/web_anon. | 4 new schemas | No overlap | Safe to ignore — domain expansion, feature 003. These schemas are not used by 019. |
| **121** `drop_unprefixed_schemas` | **DROPS** `bronze`, `raw`, `silver`, `gold`, `staging`, `mart`, `scoring` schemas CASCADE. Moves operational tables to `ops.*`. Verifies only prefixed schemas remain. | Moves ops tables, DROPS 7 schemas | **CRITICAL** — 085 references objects in these schemas? No — 085 uses only hcs_raw, hcs_silver, hcs_gold, mol_silver, mol_raw, meta. | Not a gap for 085. But note: migration 121 drops `silver.*` and `gold.*`. Any code that still references `silver.healthcare_facilities` (migration 090's target) or `silver.molecule_stage_history` will break. 019 must not introduce code referencing bare schema names. |
| **122** `align_silver_column_names` | Renames `mol_silver.molecules.smiles` to `canonical_smiles`. Adds mechanism_of_action, max_phase. Renames clinical_trials columns (title→brief_title, status→overall_status, etc.). Drops many api views first, recreates. | Column renames + view recreations | No overlap | Safe to ignore — column alignment, feature 003. 019 should not reference `mol_silver.molecules.smiles` (use `canonical_smiles`). |
| **123** `create_gold_trial_outcomes` | `mol_gold.trial_outcomes` table (referenced in code but never created). | `mol_gold.trial_outcomes` | No overlap | **GAP** — 019's research note #2 identified that `trial_outcomes.sql` on main references xenon. Migration 123 creates the table. 085 does not create this table. If feature-019 updates trial_outcomes.sql to reference mol_silver.publication_evidence, the table must exist. Since 085 doesn't create it, it must already exist on main OR 085 should create it. |
| **124** `mol_raw_sec_edgar` | `mol_raw.sec_edgar` with standard JSONB medallion schema. | `mol_raw.sec_edgar` | No overlap | Safe to ignore — SEC EDGAR raw, feature 012. |
| **125** `europepmc_integration` | `mol_raw.europepmc` — standard JSONB schema with drug_name/molecule_id. Inserts into `ops.sync_schedules`. | `mol_raw.europepmc` | **OVERLAP** — 085 creates `mol_raw.europepmc_raw` for the same purpose | **GAP** (naming): 085 uses `mol_raw.europepmc_raw`; 016 uses `mol_raw.europepmc`. The `_raw` suffix is non-standard. Recommend aligning 085 to use `mol_raw.europepmc` so it matches the pattern 016 establishes and avoids duplicate table confusion. |
| **126** `mol_missing_sources` | mol_raw + mol_bronze tables for 7 sources: bindingdb, who_inn, rxnorm, tdc_admet, pharmgkb, kegg_drug, websearch. Inserts into `ops.sync_schedules`. Grants. | `mol_raw.*` (7), `mol_bronze.*` (7) | No overlap | Safe to ignore — pharmacology/cheminformatics sources, not 019 scope. |
| **127** `clinicaltrials_queried_drug_name` | Adds `queried_drug_name` to physical bronze/silver clinical_trials tables. Recreates views. Clears auto-onboarded needs_review flag. | Column additions, view recreations | No overlap | Safe to ignore — clinical trials entity linking fix, feature 012/003. |
| **128** `mol_raw_ema_and_silver_grants` | `mol_raw.ema`. Conditional grants for pubchem, drugbank, cochrane_reviews, ema_regulatory, market_summary. Creates event trigger `auto_grant_mol_tables`. | `mol_raw.ema` | No overlap | Safe to ignore. Note: event trigger is significant infrastructure — auto-grants analyst role on new mol_silver/mol_gold tables. |
| **129** `financial_filings_mda_only` | ALTERs mol_silver.financial_filings to add drug_name/cik, drop revenue/net_income/period/product_name. Drops mol_silver.financial_data. | Column changes | No overlap | Safe to ignore. |
| **130** `mol_silver_publications` | `mol_silver.publications` table (60+ columns). `mol_silver.molecule_publications` view. Grants. Inserts openalex_ci into sync_schedules. | `mol_silver.publications`, `mol_silver.molecule_publications` | No overlap | Safe to ignore — publications table, feature 003/012. |
| **132** `stub_tables_for_targeting_and_hrsa` | `hcs_raw.hrsa_shortage_areas`. Creates `targeting` schema + 5 tables: biome_relationships, sales_coverage, volume_history, emr_systems, champions. | `hcs_raw.hrsa_shortage_areas`, `targeting.*` (5 tables) | No overlap | Safe to ignore — targeting module, not 019 scope. |
| **133** `fetch_state_table` | `ops.fetch_state` table (persistent manifest for ingestion fetchers, replaces file-based system). Grants to api_user. | `ops.fetch_state` | No overlap | **NOTE**: This table is important infrastructure — all fetchers write to it. If `ops` schema doesn't exist when 085 runs, the fetchers will fail. 085 section 8 grants on hcs_silver/hcs_gold but does not create `ops` schema. |
| **134** `cms_hcs_raw_jsonb_conversion` | **DROPS** all typed hcs_raw tables from migration 083 and recreates them with canonical JSONB pattern (response_body + hash). This is the terminal schema for hcs_raw on the 016 branch. | All hcs_raw.cms_* tables (JSONB pattern) | **CRITICAL** — This reveals the 016 branch's final hcs_raw schema: JSONB, not typed columns. 085 uses typed columns. | **DESIGN DIVERGENCE**: 016 branch ultimately chose JSONB for hcs_raw (migration 134). 085 (feature-019) keeps typed columns. Both are valid but they are incompatible. Since 019 is a fresh delta, typed columns are fine — but the team should know 016's terminal design was JSONB. If these branches ever merge, the hcs_raw schema must be reconciled. |
| **135** `fix_openfda_pharm_class` | GRANT SELECT only (no DDL) — drug_labels grant | Permission only | No overlap | Safe to ignore. |
| **136** `purple_book` | `mol_raw.purple_book`. Inserts into `ops.sync_schedules`. | `mol_raw.purple_book` | No overlap | Safe to ignore — Purple Book biologics, feature 003. |
| **137** `fix_openfda_pharm_class` (duplicate prefix 115→137) | GRANT SELECT only | Permission only | No overlap | Safe to ignore. |
| **138** `restore_raw_jsonb_pattern` | Adds standard JSONB columns to 14 mol_raw tables that had typed-only schemas (acc_tvc_certification, cochrane_reviews, ema_regulatory, epo_patents, etc.) | Column additions to 14 mol_raw tables | No overlap | Safe to ignore — JSONB restoration, feature 012. |
| **139** `missing_mol_raw_tables` | Creates mol_raw tables for ema (extended schema), orange_book, orcid, and ~15 others with full medallion schema | ~15 mol_raw tables | No overlap | Safe to ignore — molecule source infrastructure. |
| **140** `mol_gold_molecule_profile_view_and_mol_silver_patents` | Grants on `mol_gold.molecule_profile`. Creates `mol_silver.patents` table (46 columns, EPO source). | `mol_silver.patents` | No overlap | Safe to ignore — feature 012 / EPO patents. |

---

### 11.2 Objects Already Covered by Migration 085 (019 branch)

The following objects that appear in the 016 branch are **already present in 085**:

| Object | 016 Migration | 085 Coverage |
|--------|--------------|--------------|
| `hcs_raw` schema | 083, 118 | Section 1 |
| `hcs_bronze` schema | 118 | Section 1 (via CREATE SCHEMA IF NOT EXISTS) |
| `hcs_silver` schema | 085 (016), 118 | Section 1 |
| `hcs_gold` schema | 086 (016), 118 | Section 1 |
| `hcs_raw.cms_part_d_spending` | 083 | Section 2 (different column schema — flat not partitioned) |
| `hcs_raw.cms_part_b_spending` | 083 | Section 2 |
| `hcs_raw.cms_open_payments` | 083, 100 | Section 2 |
| `hcs_raw.cms_nppes` | 083 | Section 2 |
| `hcs_raw.cms_inpatient_puf` | 083 | Section 2 |
| `hcs_raw.cms_physician_puf` | 083 | Section 2 |
| `hcs_raw.cms_hospital_general_info` | 083 | Section 2 |
| `hcs_raw.*` (21 additional CMS tables) | 083 | Section 3 |
| `mol_silver.publication_evidence` | None on 016 | Section 4 (019-only) |
| `mol_silver.publication_evidence_staging` | None on 016 | Section 4 (019-only) |
| `mol_silver.physician_payments` | 110 (different schema) | Section 4 |
| `mol_silver.research_grants` | 110 (different schema) | Section 4 |
| `mol_silver.agent_quarantine` | 087 → `meta.ops_agent_quarantine` (different location) | Section 4 |
| `hcs_silver.service_lines`, `idn_hierarchy`, `referral_network`, `verified_contacts`, `staffing_decomposition`, `equipment_inventory` | 085 (016) — different table names | Section 5 |
| `meta.data_sources` INSERTs (28 CMS + 2 API sources) | 089 (uses `meta.ops_data_sources`), 011 | Section 6 |
| `mol_raw.europepmc_raw` | 125 → `mol_raw.europepmc` | Section 7 (name differs) |
| `mol_raw.nih_reporter_raw` | 111 → `mol_raw.nih_reporter` | Section 7 (name differs) |
| `web_anon` grants on hcs_silver/hcs_gold | 096, 097, 118 | Section 8 |

---

### 11.3 Objects NOT in 085 That 019 May Need

These are objects introduced by the 016 branch that feature-019's 085 migration **does not create** but which may be dependencies for 019's own code:

#### Critical Gaps

1. **`meta.ops_agent_execution_log`** (migration 087)
   - 085 creates `mol_silver.agent_quarantine` but no execution log.
   - If 019's agents write execution records, this table (or equivalent) is needed.
   - **Recommended action**: Add `meta.ops_agent_execution_log` to 085, or confirm agents write to a different table.

2. **`meta.data_sources` vs `meta.ops_data_sources`** (migration 089)
   - 085 does `INSERT INTO meta.data_sources ...` in section 6.
   - 016 branch uses `meta.ops_data_sources` as the canonical table (migration 089).
   - If main has `meta.ops_data_sources` (not `meta.data_sources`), 085's inserts will fail with "relation does not exist."
   - **Recommended action**: Verify which table name is canonical on main before running 085.

3. **`mol_gold.trial_outcomes`** (migration 123)
   - 085 does not create this table.
   - Research note #2 identifies that `trial_outcomes.sql` must be updated to reference `mol_silver.publication_evidence`.
   - If `mol_gold.trial_outcomes` does not exist on main, the updated SQLMesh model cannot deploy.
   - **Recommended action**: Add `mol_gold.trial_outcomes` DDL to 085 (it's short — UUID PK, molecule_id FK, nct_id, endpoint_name, result, phase, overall_status).

4. **`mol_raw.europepmc` naming** (migration 125 vs 085 section 7)
   - 085 creates `mol_raw.europepmc_raw` (with `_raw` suffix).
   - 016 establishes `mol_raw.europepmc` (without suffix) — consistent with all other mol_raw tables (none use `_raw` suffix).
   - If any code targets `mol_raw.europepmc`, 085's `mol_raw.europepmc_raw` will be invisible to it.
   - **Recommended action**: Rename to `mol_raw.europepmc` in 085 to match convention.

5. **`mol_raw.nih_reporter_raw` naming** (migration 111 vs 085 section 7)
   - Same issue — 016 uses `mol_raw.nih_reporter`; 085 uses `mol_raw.nih_reporter_raw`.
   - **Recommended action**: Rename to `mol_raw.nih_reporter` in 085.

#### Notable Gaps (Lower Priority)

6. **`meta.cms_staleness_report` view** (migration 089)
   - Useful monitoring view for CMS source freshness. Not in 085.
   - Low priority — can be added in a follow-up migration or Grafana alert replaces it.

7. **`ops.fetch_state` table** (migration 133)
   - Persistent manifest store for all fetchers. Not in 085.
   - If the ingestion pipeline for the 28 CMS sources needs persistent state between pod restarts, this table is required.
   - **Recommended action**: Verify if fetchers fall back to file-based manifests or require the DB table. If DB is required, add to 085.

8. **`targeting` schema and tables** (migration 132)
   - Not 019's scope, but references `hcs_raw.hrsa_shortage_areas` which is also created in 132.
   - `hcs_raw.hrsa_shortage_areas` is not in 085. If any 019 SQLMesh model references HRSA data, this table is needed.
   - Low priority — HRSA integration is out of scope for 019.

---

### 11.4 Safe to Ignore

These objects from the 016 branch are clearly out of scope for feature-019:

**CMS Data-Tools UI Layer** (088, 092, 093): The `api.*` view wrappers and 17 per-source hcs_gold views are specific to the 016 branch's `/api/v1/data-tools/{source}/query` endpoint design. Feature-019 is about reconciling the schema and building agent infrastructure, not the data-tools UI.

**Schema Drops (121)**: Migration 121 drops `bronze`, `raw`, `silver`, `gold`, `staging`, `mart`, `scoring` schemas. Feature-019 does not create objects in these schemas, so no gap.

**Molecule-specific enrichment** (109–116, 122, 124, 126–130, 135–140): These migrations enrich the mol_* medallion stack — clinical trials, financial filings, publications, patents, SEC EDGAR, Purple Book, DailyMed, etc. These are feature 003 / feature 012 scope, not 019.

**IP and trademark sources** (091, 094, 095): euipo_designs, molecule_stage_history, bronze_chembl_activities all use legacy `raw.*`/`bronze.*`/`silver.*` schemas that were dropped in 121. Dead paths.

**EuropePMC and NIH Reporter silver tables** (110, 125): These create the raw/silver infrastructure for EuropePMC and NIH Reporter in the mol_* namespace, not hcs_*. Feature-019's 085 creates equivalent raw tables — but the bronze/silver population models for EuropePMC and NIH Reporter in the mol_* path are 016-specific. The 019 approach is to have these sources flow through `hcs_raw` or `mol_raw` and land in `mol_silver.physician_payments` / `mol_silver.research_grants` via agents, not SQLMesh bronze models.

**Xenon ontology** (117): `xenon.xenon_data_source_ontology` INSERTs for CMS gold views. Feature-019 does not manage xenon — the ontology entries for CMS will be added by the xenon team separately.

**Indication/epidemiology** (113, 119, 120): `mol_silver.indication_epidemiology`, `mol_silver.indication_revenue`, `ind_silver/ind_gold` schemas, `mol_gold.indication_revenue_summary`. These are for the molecule assessment dashboard (feature 003), not for CMS PUF / healthcare system data ingestion.

**`targeting` schema** (132): Biome-specific sales targeting, not general infrastructure.

**HCS JSONB terminal schema** (134): Migration 134 is the 016 branch's final schema decision — dropping all typed hcs_raw tables and replacing with JSONB. Feature-019 intentionally diverges here: 085 keeps typed columns. This is a conscious design choice — both are valid, but they are architecturally incompatible if the branches merge without reconciliation.

---

### 11.5 Recommended Changes to Migration 085

Based on this audit, the following targeted changes are recommended:

1. **Rename `mol_raw.europepmc_raw` → `mol_raw.europepmc`** and rename index `uidx_europepmc_raw_pmid` accordingly. Aligns with the mol_raw naming convention (no `_raw` suffix on table names within the `mol_raw` schema).

2. **Rename `mol_raw.nih_reporter_raw` → `mol_raw.nih_reporter`** and rename index `uidx_nih_reporter_raw_project_num` accordingly.

3. **Add `meta.ops_agent_execution_log`** (from migration 087) or document explicitly that 019's agents do not use an execution log (using only `mol_silver.agent_quarantine`).

4. **Verify `meta.data_sources` vs `meta.ops_data_sources`** — run `\dt meta.*` on the production DB to confirm which table holds CMS source catalog entries. Update section 6 of 085 accordingly.

5. **Add `mol_gold.trial_outcomes` DDL** if it does not exist on main (check with `SELECT to_regclass('mol_gold.trial_outcomes')`). The table is simple and is needed for the trial_outcomes.sql SQLMesh model update required by FR-024a.

6. **Document the hcs_raw design divergence** from migration 134 in the spec. Feature-019 uses typed columns; 016 ultimately chose JSONB. This divergence must be resolved before any 016→main merge attempt.

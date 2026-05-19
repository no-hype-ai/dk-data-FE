# Feature Specification: Post-Deployment Fixes, SQL Audit & Silver Gap Closure

**Feature Branch**: `021-post-deploy-fixes`
**Created**: 2026-03-31
**Status**: Completed
**Issues**: [#169](https://github.com/data-kinetic/dk-data-FE/issues/169), [#170](https://github.com/data-kinetic/dk-data-FE/issues/170), [#175](https://github.com/data-kinetic/dk-data-FE/issues/175), [#176](https://github.com/data-kinetic/dk-data-FE/issues/176)

## Overview

Following the prod promotion of image `prod-85e01aa` (PRs #149, #159), a post-deployment audit expanded across the live cluster, the full ingestion source catalogue (~98 sources), and the entire SQLMesh medallion pipeline. This feature captures all fixes applied across five areas:

1. **Credential gaps** — EPO OAuth2 keys were in the wrong Doppler project; corrected via CLI. USPTO registration blocked by ID.me; sources skip gracefully.
2. **DDInter retirement** — The DDInter source has been permanently unreachable since March 2026. Fetcher, CronJob, and SOURCES registry entry removed.
3. **API endpoint and auth fixes** — EUIPO token URL, NICE header, IMGT bulk endpoint, WHO ICD-10 dead URL.
4. **WHO ICD fetcher rewrite** — Dynamic chapter discovery replaces hardcoded entity IDs; full 4-level ICD-10 tree traversal via recursive walker.
5. **SQL model audit & bug fixes (audits #175 + #176)** — 26 of 27 bugs fixed: wrong column names, grain violations, fan-out from multi-year joins, broken identifier_type references, FULL model filter anti-patterns, orphaned model chains.
6. **Silver gap closure** — 7 bronze dead-end sources promoted to silver with proper linkage strategies. 5 silver models with fan-out from multi-year joins fixed with DISTINCT ON.
7. **Operational improvements** — Per-source retry in backfill orchestration; per-source Prometheus success timestamps.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Credentials Correctly Wired to Cluster (Priority: P1)

Operations needs confidence that all API-gated sources have their credentials in the right Doppler project (`dk-data-applications/prd`) so the Doppler operator syncs them to `dk-data-secrets` and CronJobs pick them up without manual intervention.

**Acceptance Scenarios**:
1. **Given** EPO credentials exist in Doppler, **When** the EPO CronJob runs, **Then** it authenticates successfully and inserts patent records rather than returning 401
2. **Given** a key is absent or set to CHANGEME, **When** the affected fetcher runs, **Then** it exits with `source_unavailable` (exit 0) and logs a warning
3. **Given** USPTO registration is blocked, **When** USPTO CronJobs run, **Then** they skip gracefully and the issue is tracked (#170)

---

### User Story 2 — Dead Sources Retired Cleanly (Priority: P2)

DDInter has been unreachable for weeks. Keeping it active creates noise in failure logs and wastes CronJob slots.

**Acceptance Scenarios**:
1. **Given** DDInter has been retired, **When** ArgoCD syncs, **Then** the `fetch-cms-ddinter` CronJob is pruned from the cluster
2. **Given** historical `hcs_raw.cms_ddinter` data exists, **When** the bronze model runs, **Then** it still materialises that data (model retained, fetcher removed)
3. **Given** drug-drug interaction data is needed, **When** the platform is queried, **Then** DrugBank (`mol_bronze.drugbank_data`) is the authoritative source

---

### User Story 3 — All ~98 Sources Audited for Rate Limits and Pagination (Priority: P3)

A full source catalogue audit ensures every fetcher respects upstream rate limits, uses consistent pagination, and has appropriate backfill caps.

**Acceptance Scenarios**:
1. **Given** a CMS PUF source with 3 years of available data, **When** the fetcher runs with `days_back=1095`, **Then** it discovers available dataset UUIDs dynamically from the CMS catalog
2. **Given** an API source with a rate limit, **When** the fetcher exceeds the configured cap, **Then** it backs off and retries rather than returning a 429 to the caller
3. **Given** a fetcher with a backfill cap, **When** the full historical window exceeds that cap, **Then** it fetches up to the cap and logs that pagination was bounded

---

### User Story 4 — WHO ICD Codes Reliably Fetched (Priority: P2)

ICD-10 and ICD-11 codes must be fetchable via the live WHO API. The old ICD-10 endpoint was dead; hardcoded ICD-11 entity IDs were returning 404s.

**Acceptance Scenarios**:
1. **Given** WHO API credentials are set, **When** the ICD fetcher runs for ICD-10, **Then** it dynamically discovers all chapters from the root URL and walks all 4 hierarchy levels
2. **Given** a new ICD-11 release version, **When** the base URL is updated, **Then** chapter IDs are re-discovered automatically with no code changes
3. **Given** missing credentials, **When** the fetcher runs, **Then** it raises a `RuntimeError` with the WHO registration URL — it does not silently return 0 records with `status: success`

---

### User Story 5 — SQLMesh Pipeline Produces Correct Grain-Level Data (Priority: P1)

Silver and gold models must respect their declared grain. Fan-out from multi-year JOIN partners produces duplicate rows that corrupt analytics.

**Acceptance Scenarios**:
1. **Given** `hcs_silver.cms_drug_market`, **When** a generic drug has multiple HCPCS codes in Part B, **Then** they are aggregated into a single row per `(generic_name, _source_year)` with spending summed
2. **Given** any silver model with a JOIN to `cms_nppes` (grain: `npi, _source_year`), **When** multiple years exist for an NPI, **Then** exactly one row is returned per grain key (most recent year)
3. **Given** `mol_silver.imgt` with a PDB code matching multiple molecule aliases, **When** the model runs, **Then** exactly one row is produced per `pdb_code` (exact match preferred)
4. **Given** `mol_silver.patent_exclusivities` (FULL model), **When** all rows have been processed once, **Then** subsequent FULL rebuilds still return all rows (no `processed_to_silver = FALSE` filter)

---

### User Story 6 — All Bronze Dead-End Sources Have Silver Models (Priority: P2)

Every bronze source must have at least one silver model consuming it with a documented linkage strategy, so data does not stop at the bronze layer.

**Acceptance Scenarios**:
1. **Given** `hcs_bronze.cms_physician_puf_services`, **When** `hcs_silver.cms_physician_puf_services` runs, **Then** drug-flagged HCPCS codes are linked to `molecule_id` via `hcpcs_molecule_bridge`, and providers are enriched with NPPES identity
2. **Given** `hcs_bronze.cms_stabilis`, **When** `hcs_silver.cms_stabilis` runs, **Then** each drug name is resolved to a `molecule_id` via normalized alias matching
3. **Given** `mol_bronze.ema_regulatory`, **When** `mol_silver.ema_regulatory_docs` runs, **Then** each document's `active_substance` is linked to a `molecule_id` using canonical exact → alias → first-token fallback

---

### User Story 7 — Backfill Orchestration Handles Transient Failures (Priority: P3)

Individual source fetch failures during backfill should not be permanent. Transient errors (connection reset, brief API unavailability) should be retried automatically.

**Acceptance Scenarios**:
1. **Given** a transient network error during `_fetch_one`, **When** the error occurs, **Then** the fetcher retries up to 3 times with exponential backoff (30s → 60s → 120s) before failing permanently
2. **Given** a successful source fetch, **When** `_fetch_one` completes with `status: success`, **Then** `batch_job_last_success_timestamp{job="backfill_fetch_<source>"}` is emitted — enabling per-source Prometheus staleness alerts without querying `meta.data_sources`

---

## Functional Requirements

### FR-001 — EPO Credential Placement
EPO OAuth2 keys must exist in `dk-data-applications/prd` Doppler config.

### FR-002 — Graceful Credential Absence
Any fetcher whose API key is absent must return `status: "source_unavailable"`, exit 0, and log a warning.

### FR-003 — DDInter Retirement
Remove fetcher, source loader, SOURCES entry, and CronJob manifest. Retain bronze model with retirement notice.

### FR-004 — CMS PUF Multi-Year Backfill
CMS PUF fetchers must discover available dataset UUIDs from the CMS catalog API dynamically.

### FR-005 — EUIPO Token URL
EUIPO IBM Gateway token endpoint: `https://euipo.europa.eu/cas-server-webapp/oidc/accessToken`.

### FR-006 — USPTO Key Tracking
Issue #170 documents registration blocker. Fetchers continue in `source_unavailable` mode.

### FR-007 — WHO ICD Dynamic Discovery
`who_icd.py` must fetch top-level chapters by reading the `child` array from the linearization root URL. No hardcoded entity IDs. Applies to both ICD-10 and ICD-11.

### FR-008 — ICD-10 Full Tree Traversal
`_walk_icd10_node` must recurse through all 4 hierarchy levels (chapter → block → 3-char → 4-char). Only nodes with a populated `code` field are recorded.

### FR-009 — Grain Integrity in Silver Models
All silver models must honour their declared grain. Models joining to tables with a `_source_year` component in their grain (e.g., `cms_nppes`, `cms_hospital_general_info`) must use `DISTINCT ON (grain_key) ORDER BY grain_key, _source_year DESC NULLS LAST`.

### FR-010 — No `processed_to_silver` Filter in FULL Models
FULL models rebuild entirely on each run. Any `WHERE processed_to_silver = FALSE` filter in a FULL model must be removed.

### FR-011 — Correct `mol_silver.molecules` Column References
Silver and gold models must reference `canonical_name` on `mol_silver.molecules`. Columns `inn_name` and `preferred_name` do not exist.

### FR-012 — Correct `identifier_type` Values
`identifier_mappings` populates exactly: `chembl_id`, `drugbank_id`, `pubchem_cid`, `cas_number`, `unii`, `uniprot_id`, `rxcui`, `ndc`. Models referencing `pdb_ligand` or `uniprot` must be corrected.

### FR-013 — Dead-End Bronze Sources Have Silver Models
All bronze sources not consumed by any silver model must have a silver model created with:
- Declared grain and cron
- `DISTINCT ON` where any JOIN partner has `_source_year` in its grain
- Molecule linkage via `molecule_aliases` (LATERAL LIMIT 1) where applicable
- Facility/provider linkage via `cms_hospital_general_info`/`cms_nppes` where applicable

### FR-014 — Backfill Retry
`initial_backfill._fetch_one` must wrap `run_ingestion` with `retry_with_backoff(max_attempts=3, initial_delay=30, max_delay=120)`.

### FR-015 — Per-Source Success Metrics
`initial_backfill._fetch_one` must call `mark_job_success(f'backfill_fetch_{source}')` on every `success` or `partial` result.

---

## Success Criteria

- **SC-001**: EPO CronJob produces data inserts rather than 401 errors
- **SC-002**: Zero `fetch-cms-ddinter` CronJob entries in cluster after ArgoCD sync
- **SC-003**: All ~98 sources in SOURCES registry have reviewed rate-limit and pagination config
- **SC-004**: `doppler secrets --project dk-data-applications --config prd` shows no CHANGEME for EPO keys
- **SC-005**: Any fetcher with a missing key exits 0 (`source_unavailable`)
- **SC-006**: ICD-10 and ICD-11 fetchers retrieve live data via `id.who.int` with dynamic chapter discovery
- **SC-007**: All 26 confirmed SQL bugs from audits #175 and #176 are fixed; no grain violations remain in any silver model
- **SC-008**: All 7 previously dead-end bronze sources have silver models with documented linkage strategies
- **SC-009**: `batch_job_last_success_timestamp` Prometheus metric is emitted per source on successful backfill fetch
- **SC-010**: No duplicate model names across schemas (`mol_silver.healthcare_facilities` removed)

---

## Dependencies & Assumptions

- Doppler operator resync interval is 300 seconds
- `job-initial-backfill` has not been run on the cluster; HCS transform pipeline requires manual trigger
- USPTO registration requires US-based identity; April 20, 2026 legacy hub shutdown is the hard deadline
- DrugBank API key intentionally empty; XML seed (`mol_bronze.drugbank_data`) covers bulk drug data
- M5 from audit #175 (11 silver models with no gold consumer) is a feature gap, not a bug — gold models added based on analytics requirements separately
- `cms_ddinter` silver model intentionally omitted from dead-end promotion (source retired, no live data flowing)

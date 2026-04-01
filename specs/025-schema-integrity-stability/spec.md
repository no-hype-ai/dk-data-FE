# Feature Specification: Schema Integrity & Platform Stability

**Feature Branch**: `025-schema-integrity-stability`
**Created**: 2026-04-01
**Status**: Draft
**Input**: Issues #191, #189, #188, #187 — post-deployment cluster audit and local backfill testing revealed missing DDL, column name drift, OOM crashes, missing constraints, broken external API fetchers, and MCP adapter failures.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - All scheduled data ingestion jobs complete without database errors (Priority: P1)

As a data platform operator, I need every scheduled ingestion job to insert records into the database without encountering missing table, missing column, or missing constraint errors, so that no data is silently dropped during routine operations.

**Why this priority**: Missing tables and constraints are causing 0-row inserts for multiple sources (pubchem, chembl_molecules, who_gho), and column name mismatches in the refresh log mean no source has checkpoint tracking — this is the most critical data integrity issue.

**Independent Test**: Run each of the affected sources (pubchem, chembl_molecules, who_gho, cdc_vaccines) with `--max-records 100` and verify records_inserted > 0, plus verify `meta.refresh_log` has a corresponding entry with correct timestamps.

**Acceptance Scenarios**:

1. **Given** the database has `meta.refresh_log` with columns `refresh_started_at` and `refresh_completed_at`, **When** any source completes ingestion, **Then** a row is inserted into `meta.refresh_log` with non-NULL timestamps and the correct source_id.
2. **Given** `mol_raw.pubchem` has a UNIQUE constraint on `request_id`, **When** the pubchem loader runs with ON CONFLICT, **Then** records are upserted successfully and `records_inserted > 0`.
3. **Given** `mol_raw.cdc_vaccines` exists in the database, **When** the cdc_vaccines fetcher runs, **Then** records are inserted into the table without "relation does not exist" errors.
4. **Given** `dev-init.sql` and `init_database.sql` both define `meta.refresh_log`, **When** either script is used to initialize a new environment, **Then** the column names match what the ingestion code expects (`refresh_started_at`, `refresh_completed_at`).

---

### User Story 2 - Ingestion jobs do not crash with OOMKill (Priority: P1)

As a platform operator, I need CronJobs to have sufficient memory limits so they complete without being killed by the kernel OOM killer, ensuring data ingestion runs reliably on schedule.

**Why this priority**: 5 CronJobs are repeatedly OOMKilled on every scheduled run, causing complete data loss for those sources on every cycle.

**Independent Test**: Trigger each affected CronJob in the staging cluster and verify it completes with status "Succeeded" rather than "OOMKilled".

**Acceptance Scenarios**:

1. **Given** the `fetch-sider` CronJob has a memory limit of 1Gi, **When** it runs its full ingestion, **Then** it completes without OOMKill.
2. **Given** the `fetch-cms-imaging-puf` CronJob has a memory limit of 1Gi, **When** it runs, **Then** it completes without OOMKill.
3. **Given** the `fetch-cms-pecos` CronJob has a memory limit of 1Gi, **When** it runs, **Then** it completes without OOMKill.
4. **Given** the `fetch-hrsa` CronJob has a memory limit of 1Gi, **When** it runs, **Then** it completes without OOMKill.
5. **Given** the `fetch-cms-formulary` CronJob has a memory limit of 4Gi, **When** it runs, **Then** it completes without OOMKill.

---

### User Story 3 - External API fetchers handle endpoint changes gracefully (Priority: P2)

As a data engineer, I need fetchers for cochrane, openfda_faers, and imgt to either use updated API endpoints or fail with clear, actionable error messages, so that I know which sources need attention versus which are working.

**Why this priority**: These 3 fetchers fail silently or with unhelpful errors on every run, but the platform still ingests 22+ sources successfully — fixing these expands coverage but isn't blocking core operations.

**Independent Test**: Run each fetcher individually with `--max-records 10` and verify either successful data retrieval or a clear error message indicating the specific API issue.

**Acceptance Scenarios**:

1. **Given** the Cochrane API endpoint has changed, **When** the cochrane fetcher runs, **Then** it either uses the updated endpoint and returns data, or returns a structured error indicating the endpoint is unavailable (not a generic 404).
2. **Given** the OpenFDA FAERS API rejects the date range `99991231`, **When** the openfda_faers fetcher runs with a valid date range, **Then** it returns data without a 403 error.
3. **Given** the IMGT endpoint may have moved, **When** the imgt fetcher runs, **Then** it either retrieves data from the correct URL or returns a clear "source unavailable" status with the attempted URL.

---

### User Story 4 - MCP data-tool adapters return useful responses (Priority: P3)

As an analyst using the MCP data-tool interface, I need each adapter to either return valid JSON results or a clear explanation of why results aren't available, so that I can distinguish between "no data found" and "adapter is broken".

**Why this priority**: 8 of 61 adapters are failing, but the MCP layer is a convenience interface — data is still available through the main ingestion pipeline. Fixing these improves analyst experience.

**Independent Test**: Invoke each of the 8 affected adapters via `POST /api/v1/data-tools/{tool}/invoke` with `{"drug_name": "imatinib"}` and verify either a 200 with JSON results or a structured error response (not a 500).

**Acceptance Scenarios**:

1. **Given** the base_tool follows redirects and sends `Accept: application/json`, **When** any adapter makes an HTTP request, **Then** redirects are followed and JSON is requested by default.
2. **Given** the response is not JSON, **When** base_tool processes it, **Then** a structured error is returned instead of a JSONDecodeError 500.
3. **Given** a fixable adapter (fda_drugs, pdb_structures, orcid, cms_part_d_spending, hta_decisions) has its `build_url()` override, **When** invoked, **Then** it returns valid JSON results for known drugs.
4. **Given** a bulk-only adapter (ema, cochrane, ttd), **When** invoked, **Then** it returns a clear message explaining the source is only available via bulk download, not a 500 error.

---

### User Story 5 - Schema consistency across all medallion layers (Priority: P1)

As a data platform maintainer, I need all table names to use proper domain prefixes and all columns present in raw tables to flow through to bronze, so that no data is silently lost during transformation.

**Why this priority**: This is a foundational data integrity requirement. If columns are dropped between layers, downstream analytics produce incorrect or incomplete results without any error signal.

**Independent Test**: For each raw table, compare its column list against the corresponding bronze model's SELECT list and verify no columns are missing. Verify all table names follow the prefix convention.

**Acceptance Scenarios**:

1. **Given** a raw table with N columns, **When** the corresponding bronze model transforms it, **Then** all N columns (or their explicitly documented transformations) appear in the bronze output.
2. **Given** the table prefix convention (mol_raw, mol_bronze, mol_silver, mol_gold, hcs_raw, hcs_bronze, hcs_silver, hcs_gold, ind_raw, ind_bronze, ind_silver, ind_gold), **When** any table or model is created, **Then** it uses the correct domain prefix for its layer and domain.
3. **Given** an external API returns fields with specific names, **When** data flows from fetcher to raw table to bronze to silver, **Then** the column names are traceable back to the original API field names (with documented camelCase-to-snake_case conversions only).

---

### Edge Cases

- What happens when a raw table is created by migration but the corresponding bronze SQLMesh model references columns that don't exist in the DDL?
- How does the system handle a fetcher that returns new fields not present in the raw table schema?
- What happens when two initialization scripts (dev-init.sql vs init_database.sql) create the same table with different column names and a developer uses the wrong one?
- What happens when a CronJob's memory limit is increased but the cluster node doesn't have enough allocatable memory?

## Requirements *(mandatory)*

### Functional Requirements

#### Schema & DDL Integrity
- **FR-001**: System MUST have consistent column names for `meta.refresh_log` across all initialization scripts — `dev-init.sql`, `init_database.sql`, and migration 083 MUST all use `refresh_started_at` and `refresh_completed_at`.
- **FR-002**: System MUST have a UNIQUE constraint on `mol_raw.pubchem(request_id)` to support the loader's ON CONFLICT clause.
- **FR-003**: System MUST have UNIQUE constraints on any other mol_raw or hcs_raw tables where the loader uses ON CONFLICT, including `chembl_molecules` and `who_gho`.
- **FR-004**: The `mol_raw.cdc_vaccines` table MUST exist in the database (verify migration 121 is applied or add to next migration). A corresponding row MUST exist in `meta.data_sources` with `source_name = 'cdc_vaccines'` for the ingestion orchestrator to resolve the source_id.
- **FR-005**: All raw, bronze, silver, and gold tables MUST use the correct domain prefix (mol_, hcs_, ind_) for their domain and layer.

#### Column Completeness
- **FR-006**: Bronze SQLMesh models MUST NOT drop any columns that exist in their corresponding raw table DDL, unless the omission is explicitly documented with a rationale.
- **FR-007**: External API response field names MUST be the authoritative source for raw table column names. Only camelCase-to-snake_case conversion is permitted; no arbitrary renames.
- **FR-008**: Fetcher INSERT column lists MUST match their target raw table DDL exactly — no extra columns, no missing columns.

#### CronJob Resource Limits
- **FR-009**: `fetch-sider` CronJob MUST have memory limit of at least 1Gi.
- **FR-010**: `fetch-cms-imaging-puf` CronJob MUST have memory limit of at least 1Gi.
- **FR-011**: `fetch-cms-pecos` CronJob MUST have memory limit of at least 1Gi.
- **FR-012**: `fetch-hrsa` CronJob MUST have memory limit of at least 1Gi.
- **FR-013**: `fetch-cms-formulary` CronJob MUST have memory limit of at least 4Gi.

#### External API Fetchers
- **FR-014**: The cochrane fetcher MUST handle the 404 from the removed `/api/search` endpoint — either by using an updated URL or by clearly marking the source as unavailable.
- **FR-015**: The openfda_faers fetcher MUST use a valid date range upper bound (not `99991231`).
- **FR-016**: The imgt fetcher MUST verify its target URL is reachable and return a clear status if not.

#### MCP Data-Tool Adapters
- **FR-017**: `base_tool.py` MUST default to `follow_redirects=True` for HTTP requests.
- **FR-018**: `base_tool.py` MUST send `Accept: application/json` as a default header.
- **FR-019**: `base_tool.py` MUST check response Content-Type before calling `response.json()` and return a structured error for non-JSON responses.
- **FR-020**: The 5 fixable adapters (fda_drugs, pdb_structures, orcid, cms_part_d_spending, hta_decisions) MUST override `build_url()` with correct API parameters.
- **FR-021**: The 3 bulk-only adapters (ema, cochrane, ttd) MUST return a structured "bulk-only source" message instead of a 500 error.

### Key Entities

- **Raw Table**: The landing zone for external API data. Each source has exactly one raw table in the appropriate domain schema (mol_raw, hcs_raw, ind_raw). Column names mirror the external API response fields.
- **Bronze Model**: A SQLMesh SQL model that reads from a raw table, applies type casting and basic cleaning. Must preserve all raw columns.
- **Refresh Log Entry**: A record in `meta.refresh_log` tracking when a source was last ingested, how many records were fetched/inserted, and the status. Critical for checkpoint-based incremental ingestion.
- **CronJob**: A Kubernetes CronJob manifest that triggers a data ingestion run on a schedule. Defines resource limits (CPU, memory) for the job container.
- **MCP Adapter**: A class that wraps an external API for on-demand querying via the MCP data-tool interface. Each adapter implements `build_url()` to construct the correct API request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 61+ data sources that previously worked continue to ingest successfully (zero regressions).
- **SC-002**: The 3 sources blocked by missing constraints (pubchem, chembl_molecules, who_gho) insert >0 records on each run.
- **SC-003**: `meta.refresh_log` records a row for every source ingestion with non-NULL start/end timestamps.
- **SC-004**: Zero OOMKill events for the 5 affected CronJobs over a 7-day observation period.
- **SC-005**: At least 2 of the 3 broken external API fetchers return data (cochrane may remain unavailable if the API is permanently removed).
- **SC-006**: 53 of 61 MCP adapters return valid responses (5 newly fixed + 48 already working), with the remaining 8 returning structured error messages instead of 500s.
- **SC-007**: Zero tables or models use incorrect domain prefixes.
- **SC-008**: Zero columns dropped between raw and bronze layers without documented rationale.

## Assumptions

- Migration 121 (which creates `mol_raw.cdc_vaccines`) may not have been applied to the cluster due to the baselined migration issue. If so, migration 137 or a new migration will create it.
- The Cochrane Library API may be permanently removed. If so, the fetcher will be marked as unavailable rather than fixed.
- Memory limit increases for CronJobs are within the cluster's allocatable resources.
- The `init_database.sql` column names (`refresh_started_at`, `refresh_completed_at`) are the authoritative version, matching the application code.
- Column name corrections from migrations 087 and 091 have been applied to the cluster.

## Out of Scope

- 17 silver models with no gold consumer (feature gap, tracked in #187 as L1-L2)
- 3 legacy HCS bronze duplicates (cms_inpatient, cms_cost_reports, cms_hospital_info)
- `drug_synonyms` / `who_inn_names` model consolidation
- MedDRA SOC data (blocked on license, deferred per #174)
- Timeout issues for slow sources (pdb, bindingdb, kegg_drug) — operational tuning, not bugs
- Sources requiring external credentials (epo_ops, ttd bulk, euipo)

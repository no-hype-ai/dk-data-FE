# Feature Specification: USPTO & EUIPO Model Datasource Integration

**Feature Branch**: `014-uspto-euipo-model-datasource`
**Created**: 2026-02-16
**Status**: Draft
**Input**: Integrate USPTO and EUIPO into dk-data-FE as model datasources per GitHub issue dk-data#143. Reorganize existing USPTO pipeline (2 fetchers: uspto_ci + uspto_patents, and EPO OPS) to complete the medallion architecture (raw->bronze->silver->gold). Add EUIPO (European Union Intellectual Property Office) trademark registry as a new data source.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - USPTO Patent Data Flows Through Full Medallion Pipeline (Priority: P1)

As a data analyst, I need USPTO patent data (from both the CI and credential-gated fetchers) to flow through the complete medallion architecture (raw → bronze → silver → gold) so that patent intelligence is available in unified silver/gold tables alongside DrugBank and EPO data for competitive analysis.

**Why this priority**: The existing USPTO bronze model is non-functional (expects JSONB `response_body` but the raw table stores flat columns). This is the core issue referenced in dk-data#143. Without fixing this, ~10,000+ patent records in `raw.uspto_patents` and `raw.uspto_ci` are inaccessible to downstream models.

**Independent Test**: Can be fully tested by running SQLMesh `plan` and `apply` against a database seeded with existing raw USPTO data, then querying `bronze.uspto_patents`, `bronze.uspto_ci`, and `silver.patents` to verify records appear with correct schema.

**Acceptance Scenarios**:

1. **Given** existing records in `raw.uspto_patents` with flat columns (patent_number, title, abstract, etc.), **When** SQLMesh runs the bronze model, **Then** `bronze.uspto_patents` contains typed, validated records matching the raw data with no JSONB parsing errors.
2. **Given** existing records in `raw.uspto_ci` with flat columns (patent_id, title, etc.), **When** SQLMesh runs the new bronze model, **Then** `bronze.uspto_ci` contains typed records with normalized column names.
3. **Given** populated `bronze.uspto_patents` and `bronze.uspto_ci` tables, **When** SQLMesh runs the silver model, **Then** `silver.patents` contains deduplicated patent records from USPTO alongside existing DrugBank patents.
4. **Given** a patent exists in both `bronze.uspto_patents` and `bronze.drugbank`, **When** `silver.patents` is computed, **Then** the record is deduplicated with a deterministic source priority.

---

### User Story 2 - EPO Patent Data Completes Medallion Pipeline (Priority: P1)

As a data analyst, I need EPO OPS patent data to have a bronze model and be included in `silver.patents` so that European patent intelligence is unified with USPTO and DrugBank data.

**Why this priority**: EPO data is already being fetched and stored in `raw.epo_patents` but has no bronze model and is not wired into silver, making it a dead-end pipeline. Completing this is low-effort with high data value.

**Independent Test**: Can be tested by seeding `raw.epo_patents` with sample records and verifying `bronze.epo_patents` and `silver.patents` contain the expected EPO records after SQLMesh runs.

**Acceptance Scenarios**:

1. **Given** records in `raw.epo_patents` with flat columns (publication_id, title, abstract, applicants, etc.), **When** SQLMesh runs the new bronze model, **Then** `bronze.epo_patents` contains typed records with normalized column names.
2. **Given** populated `bronze.epo_patents`, **When** SQLMesh runs the silver model, **Then** `silver.patents` includes EPO records with `source = 'epo_ops'`.

---

### User Story 3 - EUIPO Trademark Data Ingestion (Priority: P2)

As a data analyst, I need European Union trademark data from EUIPO (via TMview federated search or IBM API Gateway) to be ingested, stored, and processed through the medallion pipeline so that IP trademark intelligence is available for molecule lifecycle and competitive analysis.

**Why this priority**: EUIPO is a net-new data source. It provides trademark data (complementary to patent data) that enhances the IP landscape view. Lower priority than fixing existing broken pipelines but critical for full IP coverage.

**Independent Test**: Can be tested by running the EUIPO fetcher with mocked HTTP responses, verifying records are written to `raw.euipo_trademarks`, and then running SQLMesh to verify `bronze.euipo_trademarks` and `silver.trademarks` contain the expected records.

**Acceptance Scenarios**:

1. **Given** a configured EUIPO fetcher, **When** the fetcher runs against the TMview API (or EUIPO IBM API Gateway) filtered by Nice Class 5 (pharmaceutical), **Then** trademark records are returned with application_number, mark_name, applicant, status, filing_date, and Nice class information.
2. **Given** fetched EUIPO trademark records, **When** the loader writes to `raw.euipo_trademarks`, **Then** records are upserted by application_number with no duplicates.
3. **Given** records in `raw.euipo_trademarks`, **When** SQLMesh runs the bronze and silver models, **Then** `silver.trademarks` contains typed, validated trademark records.
4. **Given** the EUIPO API is unavailable (HTTP 500), **When** the fetcher runs, **Then** the fetch fails gracefully with logged errors and zero records stored, without crashing the pipeline.

---

### User Story 4 - USPTO Trademark Data Ingestion (Priority: P2)

As a data analyst, I need US trademark data from the USPTO (via TSDR API and/or Bulk Data XML downloads) to be ingested and processed through the medallion pipeline so that US pharmaceutical trademark intelligence is available alongside EU trademarks in `silver.trademarks`.

**Why this priority**: USPTO trademarks complement EUIPO trademarks for complete IP coverage. The TSDR API is well-documented with a Swagger spec, but requires an API key and is lookup-only (no search by Nice Class), so a hybrid bulk data + TSDR approach is needed.

**Independent Test**: Can be tested by running the USPTO trademark fetcher with mocked HTTP responses (TSDR multi-case endpoint) and verifying records flow through `raw.uspto_trademarks` → `bronze.uspto_trademarks` → `silver.trademarks`.

**Acceptance Scenarios**:

1. **Given** a configured USPTO trademark fetcher with a TSDR API key, **When** the fetcher runs against `https://tsdrapi.uspto.gov/ts/cd/caseMultiStatus/sn`, **Then** trademark records are returned with serial_number, mark_element, status, filing_date, registration_date, Nice classes, and owner information.
2. **Given** fetched USPTO trademark records, **When** the loader writes to `raw.uspto_trademarks`, **Then** records are upserted by serial_number with no duplicates.
3. **Given** records in `raw.uspto_trademarks`, **When** SQLMesh runs the bronze and silver models, **Then** `silver.trademarks` contains both US and EU trademark records with a `source` column distinguishing them.
4. **Given** the TSDR API returns a 401 (bad API key), **When** the fetcher runs, **Then** the fetch fails gracefully with a logged error.

---

### User Story 5 - Operational Observability for Patent & Trademark Sources (Priority: P2)

As a platform operator, I need all patent and trademark data sources (USPTO CI, USPTO Patents, EPO OPS, USPTO Trademarks, EUIPO Trademarks) to appear in Prometheus metrics and Grafana dashboards so that I can monitor ingestion health, record counts by layer, and detect pipeline failures.

**Why this priority**: Without metrics integration, pipeline failures go undetected. The existing metrics system already tracks other sources but omits all patent/trademark sources.

**Independent Test**: Can be tested by querying the `/metrics` endpoint and verifying that labels for `uspto_patents`, `uspto_ci`, `epo_patents`, `uspto_trademarks`, and `euipo_trademarks` appear in `dk_source_health_status`, `dk_raw_unprocessed_total`, and `dk_table_record_count` gauges.

**Acceptance Scenarios**:

1. **Given** the metrics endpoint is running, **When** I query `/metrics`, **Then** I see `dk_source_health_status` gauges for all 5 IP sources: `uspto_patents`, `uspto_ci`, `epo_patents`, `uspto_trademarks`, and `euipo_trademarks`.
2. **Given** records exist in `raw.euipo_trademarks`, **When** I query `/metrics`, **Then** I see `dk_table_record_count{layer="raw",table_name="euipo_trademarks"}` with the correct count.
3. **Given** bronze and silver tables are populated, **When** I query `/metrics`, **Then** `dk_table_record_count` gauges exist for bronze and silver patent/trademark tables.

---

### User Story 6 - Automated Trademark Ingestion via Kubernetes CronJobs (Priority: P3)

As a platform operator, I need EUIPO and USPTO trademark ingestion to run on automated weekly schedules via Kubernetes CronJobs, consistent with the existing USPTO patent and EPO CronJob patterns.

**Why this priority**: Automation is required for production readiness but can be added after the core pipeline is proven to work end-to-end.

**Independent Test**: Can be tested by validating the CronJob manifests with `kubectl kustomize` and verifying the schedule, image, and environment variable configuration.

**Acceptance Scenarios**:

1. **Given** EUIPO and USPTO trademark CronJob manifests, **When** `kubectl kustomize k8s/overlays/staging` is run, **Then** both manifests validate successfully with correct schedules, image references, and required secrets.
2. **Given** the CronJobs trigger, **When** the trademark fetches complete, **Then** jobs exit with code 0 on success and code 1 on failure.

---

### User Story 7 - CI/CD Validates All Patent & Trademark Components (Priority: P3)

As a developer, I need all new fetchers, loaders, validators, and models to be covered by automated tests that run on every pull request so that regressions are caught before merge.

**Why this priority**: Test coverage ensures long-term maintainability but is not blocking initial deployment if manual testing is done.

**Independent Test**: Can be tested by running `pytest tests/ -v --tb=short` and verifying that new test files for EUIPO fetcher, EUIPO validator, bronze model contracts, and silver model contracts all pass.

**Acceptance Scenarios**:

1. **Given** a PR that modifies EUIPO or USPTO code, **When** CI runs, **Then** all new and existing tests pass with `ruff check .` and `pytest tests/`.
2. **Given** a new EUIPO fetcher test file, **When** pytest auto-discovers it, **Then** at least 12 tests execute (7 fetcher + 5 validator).

---

### Edge Cases

- What happens when the PatentsView API returns malformed JSON or an unexpected schema change? The fetcher must log a warning and skip malformed records without crashing.
- What happens when EUIPO returns paginated results exceeding 10,000 records? The fetcher must respect a configurable max_records limit and stop pagination.
- What happens when `silver.patents` encounters the same patent number from multiple sources (e.g., DrugBank + USPTO)? Deduplication uses `DISTINCT ON (patent_number)` with a deterministic source priority order.
- What happens when a CronJob runs but the database is unreachable? The job must exit with code 1 and the failure must be visible in Prometheus metrics via `dk_source_health_status`.
- What happens when `raw.euipo_trademarks` receives a record with a NULL application_number? The Pydantic validator must reject it before insertion.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST refactor `bronze.uspto_patents` SQLMesh model to read from the flat-column `raw.uspto_patents` table (patent_number, title, abstract, etc.) instead of attempting to parse JSONB `response_body`.
- **FR-002**: System MUST create a new `bronze.uspto_ci` SQLMesh model that reads from the flat-column `raw.uspto_ci` table and normalizes column names to match the bronze patent schema.
- **FR-003**: System MUST create a new `bronze.epo_patents` SQLMesh model that reads from the flat-column `raw.epo_patents` table with normalized column names.
- **FR-004**: System MUST update `silver.patents` SQLMesh model to UNION ALL records from `bronze.uspto_patents`, `bronze.uspto_ci`, `bronze.epo_patents`, and existing `bronze.drugbank` sources, with deduplication via `DISTINCT ON (patent_number)` and deterministic source priority.
- **FR-005**: System MUST create a new USPTO trademark fetcher class extending `BaseFetcher` that queries the TSDR API (`tsdrapi.uspto.gov`) for trademark case status data using the multi-case batch endpoint, with API key authentication.
- **FR-005a**: System MUST create a new `USPTOTrademarkRecord` Pydantic validator with `serial_number` as a required non-empty string primary key and optional fields for mark_element, mark_type, status, status_date, filing_date, registration_number, registration_date, nice_classes (international), us_classes, owner_name, owner_entity_type, goods_and_services.
- **FR-005b**: System MUST create a loader function (following the existing `sources/epo_ops.py` pattern: internal `get_connection()`, Pydantic validation, batch commits, returns status dict) that upserts USPTO trademark records into `raw.uspto_trademarks` with `ON CONFLICT (serial_number) DO UPDATE`.
- **FR-005c**: System MUST create a database migration for `raw.uspto_trademarks` with appropriate columns and indexes.
- **FR-005d**: System MUST create `bronze.uspto_trademarks` SQLMesh model that transforms raw USPTO trademark data into typed bronze records.
- **FR-006**: System MUST create a new EUIPO fetcher class extending `BaseFetcher` that supports both the TMview API and the EUIPO IBM API Gateway, selectable via a configuration flag. The fetcher queries for trademarks filtered by Nice Class 5 (pharmaceutical preparations). IBM API Gateway is preferred when credentials are available; TMview is the fallback.
- **FR-006a**: System MUST create a new `EUIPOTrademarkRecord` Pydantic validator with `application_number` as a required non-empty string primary key and optional fields for mark_name, mark_kind, mark_feature, mark_basis, applicant, representative, status (18 EUIPO status values), filing_date, registration_date, expiry_date, nice_classes, and goods_and_services.
- **FR-006b**: System MUST create a new loader function (following the existing `sources/epo_ops.py` pattern) that upserts EUIPO trademark records into `raw.euipo_trademarks` with `ON CONFLICT (application_number) DO UPDATE`.
- **FR-006c**: System MUST create a database migration that creates the `raw.euipo_trademarks` table with appropriate columns and indexes.
- **FR-006d**: System MUST create `bronze.euipo_trademarks` SQLMesh model that transforms raw EUIPO trademark data into typed bronze records.
- **FR-007**: System MUST create `silver.trademarks` SQLMesh model to UNION ALL records from `bronze.uspto_trademarks` and `bronze.euipo_trademarks` with a `source` column distinguishing US from EU trademarks. Deduplication is within-registry only (by PK per source); no cross-registry deduplication is performed — the same mark registered in both USPTO and EUIPO results in two separate silver records.
- **FR-008**: System MUST register both the USPTO trademark fetcher and EUIPO trademark fetcher in the `FETCHERS` dict in `fetch_data.py` with appropriate priority.
- **FR-009**: System MUST add both `uspto_trademarks` and `euipo_trademarks` to the `seed_data_sources.sql` seed data.
- **FR-010**: System MUST update `metrics.py` to include all 5 IP sources (`uspto_patents`, `uspto_ci`, `epo_patents`, `uspto_trademarks`, `euipo_trademarks`) in source health tracking, unprocessed count tracking, layer record counts, and external API health dicts.
- **FR-011**: System MUST create Kubernetes CronJob manifests for both USPTO trademark and EUIPO trademark ingestion following the existing CronJob pattern (weekly schedule, image reference, required secrets).
- **FR-012**: System MUST include at least 12 tests for the EUIPO trademark fetcher and validator, and at least 14 tests for the USPTO trademark fetcher and validator, following the existing test patterns (mocked HTTP, Pydantic validation).
- **FR-013**: System MUST throttle EUIPO API requests to no more than 30 requests per minute, and USPTO TSDR API requests to no more than 60 requests per minute (4 per minute for multi-case batch), to respect rate limits.
- **FR-014**: System MUST maintain a `trademark_status_history` table (in raw schema) that records status changes for both USPTO and EUIPO trademarks. Each ingestion run compares the fetched status against the last recorded status; if different, a new history row is inserted with the trademark identifier, old_status, new_status, and change_detected_at timestamp.
- **FR-015**: System MUST update `gold.molecule_profile` to include an IP trademark section that aggregates trademark data from `silver.trademarks`, linked to molecules via `silver.molecule_aliases` (matching trademark `mark_name` against known brand names, trade names, and product names — NOT generic/INN names, since trademarks are registered under brand names). The section MUST include trademark count (US + EU), active/registered count, and latest status per registry for each molecule.

### Key Entities

- **Patent**: A granted or published patent record with patent_number (PK), title, abstract, inventors, assignees, filing_date, grant_date, CPC/IPC codes, claims_count, and source provenance. Sourced from USPTO PatentsView (2 fetchers) and EPO OPS. Unified in `silver.patents`.
- **US Trademark**: A US trademark registration/application with serial_number (PK), mark_element, mark_type, status, filing_date, registration_number, registration_date, Nice classes, US classes, owner, and goods_and_services. Sourced from USPTO TSDR API + Bulk Data. Stored in `silver.trademarks` with `source = 'uspto_trademarks'`.
- **EU Trademark**: A European Union trademark registration with application_number (PK), mark_name, mark_type, applicant_name, representative_name, nice_classes, status, filing_date, registration_date, expiry_date, and goods_and_services description. Sourced from TMview/EUIPO API. Stored in `silver.trademarks` with `source = 'euipo_trademarks'`.
- **Trademark Status History**: A record of a trademark status change with trademark_identifier (FK), source (USPTO or EUIPO), old_status, new_status, and change_detected_at timestamp. Populated during each ingestion run by comparing fetched status against last recorded status.
- **Data Source**: A registered data source entry in `meta.data_sources` with source name, type, refresh schedule, and health status. Used by the metrics system for Grafana dashboards.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing patent records in `raw.uspto_patents` (currently ~10,000+) are accessible through `bronze.uspto_patents` and appear in `silver.patents` after a SQLMesh run, with zero data loss.
- **SC-002**: `silver.patents` unifies patent records from 4 sources (DrugBank, USPTO Patents, USPTO CI, EPO OPS) with correct deduplication — no duplicate patent_numbers in the silver table.
- **SC-003**: EUIPO fetcher successfully ingests at least 100 pharmaceutical trademark records (Nice Class 5) from the TMview API in a single run.
- **SC-004**: All 5 IP data sources (USPTO CI, USPTO Patents, EPO OPS, USPTO Trademarks, EUIPO Trademarks) appear in Prometheus metrics at the `/metrics` endpoint with correct record counts per layer (raw, bronze, silver).
- **SC-005**: CI/CD pipeline passes on PRs with at least 12 new EUIPO tests, at least 14 new USPTO trademark tests, and all existing USPTO/EPO tests continuing to pass.
- **SC-006**: Kubernetes CronJob manifests for all patent/trademark sources validate successfully with `kubectl kustomize`.
- **SC-007**: EUIPO API requests are throttled to no more than 30 requests per minute, preventing rate limit violations.
- **SC-008**: End-to-end pipeline latency from raw ingestion to silver table availability is under 10 minutes for incremental runs.

## Clarifications

### Session 2026-02-16

- Q: Should `silver.trademarks` deduplicate cross-registry (same mark in both USPTO and EUIPO)? → A: No. Keep both records (one per registry) with `source` column. No cross-registry deduplication — provenance preserved per registry.
- Q: Should the EUIPO fetcher target TMview API or IBM API Gateway? → A: Support both. Fetcher accepts a config flag to switch between TMview and IBM Gateway at runtime. IBM Gateway preferred if credentials exist (dk-data backend already uses it).
- Q: Should we track only current trademark status or maintain status history? → A: Status history. Add a `trademark_status_history` table tracking status changes with timestamps for both USPTO and EUIPO trademarks.
- Q: What scope for the USPTO trademark initial bulk load from XML? → A: All active Class 5 trademarks regardless of age (~200K+ records). Comprehensive coverage, no date cutoff.
- Q: Should trademark data feed into the gold layer (`gold.molecule_profile`) in this iteration? → A: Yes. Add trademark counts and status summary to the IP section of `gold.molecule_profile`, linking trademarks to molecules by drug name matching.

## Assumptions

- The EUIPO fetcher supports both the IBM API Gateway (`api.euipo.europa.eu/trademark-search` with OAuth2 + IBM Client ID) and the TMview API (`tmdn.org/tmview/api/search`), selectable at runtime via configuration. IBM Gateway is preferred if dk-data credentials exist in Doppler; TMview serves as fallback.
- The USPTO TSDR API requires an API key registered at `account.uspto.gov/api-manager/`. The key `USPTO_TSDR_API_KEY` must be provisioned in Doppler.
- The USPTO TSDR API is a lookup-only API (no search by Nice Class). Initial Class 5 dataset will be populated via Bulk Data XML download covering **all active Class 5 trademarks** (~200K+ records, no date cutoff), with TSDR used for weekly incremental updates of known cases thereafter.
- The existing PatentsView API v1 endpoints remain stable and backward-compatible.
- The existing flat-column schemas in `raw.uspto_patents`, `raw.uspto_ci`, and `raw.epo_patents` are correct and complete — no loader changes are needed.
- SQLMesh incremental models can process the existing backlog of unprocessed raw records on first run.
- Doppler secrets `EUIPO_API_KEY`/`EUIPO_SECRET_KEY` (for EUIPO IBM Gateway or TMview) and `USPTO_TSDR_API_KEY` (for TSDR) will be provisioned before deployment.
- Nice Class 5 (pharmaceutical preparations) is the primary filter for EUIPO; Classes 10, 42, and 44 may be added in future iterations.

## Dependencies

- **dk-data#143**: Original issue requesting USPTO reorganization to model datasource
- **dk-data#424**: EUIPO ETL + Database Schema migration (backend)
- **dk-data#422**: USPTO ETL + Database Schema migration (backend, closed)
- **dk-data#436**: USPTO Fast Track Datasource migration (backend)
- **dk-data#419**: Epic: Complete ETL Datasource Migration (backend)

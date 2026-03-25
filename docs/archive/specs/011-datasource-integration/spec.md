# Feature Specification: Data Source Integration

**Feature Branch**: `011-datasource-integration`
**Created**: 2026-02-14
**Status**: Draft
**Input**: Comprehensive data source integration roadmap covering 33 remaining data sources across tiers 2-4

## Clarifications

### Session 2026-02-14

- Q: How should CI source fetches be scoped — broad ingest, query-scoped, fixed, or hybrid? → A: Hybrid — broad daily ingest for high-priority CI sources (PubMed, OpenAlex), query-scoped fetches based on configurable drug/therapeutic-area terms for the rest.
- Q: Should Tier 2A/3 molecule sources get individual CronJobs or join existing grouped jobs? → A: Add to existing grouped CronJobs (`mol-fetch-weekly`/`mol-fetch-monthly`), consistent with the established molecule pipeline pattern. No new manifests needed for molecule sources.
- Q: Should all new sources get PostgREST API views, or only CI sources? → A: CI views only — create API views only for Tier 4 CI sources. Molecule sources (Tier 2A/3) defer API view creation to the SQLMesh gold-level views (separate feature).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Enable No-Blocker Molecule Sources (Priority: P1)

As a data analyst, I need BindingDB, Orange Book, SIDER, TDC ADMET, and EMA data sources enabled so that the molecule platform has foundational drug-target binding, FDA approvals, side effects, ADMET benchmarks, and European regulatory data available for queries.

**Why this priority**: These 5 sources already have complete ingestion code in `raw_ingestion.py`. They only need CronJob manifests, seed SQL, and catalog metadata — the lowest effort for the highest immediate data coverage gain.

**Independent Test**: Can be tested by triggering each source's CronJob manually and verifying records appear in `mol_raw.*` tables and catalog metadata is updated.

**Acceptance Scenarios**:

1. **Given** the BindingDB, Orange Book, SIDER, TDC ADMET, and EMA ingestion classes exist in `raw_ingestion.py`, **When** they are registered in the existing grouped molecule CronJobs and seed SQL is deployed, **Then** each source fetches data on schedule and populates its `mol_raw.*` table with at least 1 record.
2. **Given** a newly enabled source has run successfully, **When** the catalog-refresh job executes, **Then** the source appears in `meta.data_sources` with correct topic tags, staleness threshold, and health status.
3. **Given** a source fetch fails (network error, upstream API down), **When** the CronJob retries up to `backoffLimit`, **Then** the failure is recorded in `meta.batch_job_runs` with an error message and the source health status reflects the failure.

---

### User Story 2 - Enable Additional Molecule Sources (Priority: P2)

As a data analyst, I need RxNorm, DailyMed, FDA Drugs@FDA, KEGG Drug, TTD, PharmGKB, IMGT, and CDC Vaccines data sources enabled so that the platform provides comprehensive drug nomenclature, labeling, approvals, pathways, targets, pharmacogenomics, antibody structures, and vaccine data.

**Why this priority**: These 8 sources also have complete ingestion code. Enabling them broadens the molecule dataset significantly, covering drug identification (RxNorm), regulatory labeling (DailyMed), target pathways (KEGG, TTD), and pharmacogenomics (PharmGKB).

**Independent Test**: Can be tested identically to P1 — trigger CronJobs, verify `mol_raw.*` table population, and confirm catalog metadata.

**Acceptance Scenarios**:

1. **Given** the 8 additional molecule ingestion classes exist in `raw_ingestion.py`, **When** they are registered in the existing grouped molecule CronJobs and seed SQL is deployed, **Then** each source fetches data on its configured schedule and populates its `mol_raw.*` table.
2. **Given** all Tier 3 sources are active, **When** querying the data catalog API, **Then** all 8 sources appear with accurate descriptions, topic tags, and freshness status.

---

### User Story 3 - Implement High-Impact CI Sources (Priority: P3)

As a competitive intelligence analyst, I need PubMed/MEDLINE, OpenAlex, and EMA Regulatory data ingested so that the platform monitors new publications, citation networks, and European regulatory decisions relevant to drug development.

**Why this priority**: These 3 sources represent the highest-value competitive intelligence data, covering ~20% of CI monitoring needs (publications) and regulatory tracking. They require full implementation (fetcher, loader, validator, tables, tests) but deliver the most analytical value.

**Independent Test**: Can be tested by running the fetcher with a specific therapeutic-area query and verifying structured records land in `raw.*` tables with correct deduplication.

**Acceptance Scenarios**:

1. **Given** the PubMed fetcher is implemented with NCBI E-utilities using broad daily ingest, **When** a daily fetch runs, **Then** all recent pharma-relevant article metadata (PMID, title, abstract, authors, MeSH terms) is stored in the raw table with deduplication on PMID.
2. **Given** the OpenAlex CI fetcher is implemented using broad daily ingest, **When** a daily fetch runs, **Then** recent publication works with DOIs, citation counts, and concept tags are stored with deduplication on OpenAlex work ID.
3. **Given** the EMA Regulatory CI fetcher is implemented, **When** a weekly fetch runs, **Then** CHMP opinions, EPAR documents, and safety signals are stored with deduplication on EMA document ID.

---

### User Story 4 - Enable Credential-Gated Sources (Priority: P4)

As a data platform administrator, I need DrugBank, USPTO Patents, PDB, and ORCID data sources enabled once their credentials are obtained, so that proprietary drug data, patent monitoring, protein structures, and researcher profiles are available.

**Why this priority**: These sources provide high-value data but are blocked by credential acquisition (commercial licenses, API key applications, OAuth registrations). Implementation can proceed in parallel with credential procurement.

**Independent Test**: Can be tested by configuring credentials in Doppler staging environment, triggering the CronJob, and verifying data lands in the appropriate raw tables.

**Acceptance Scenarios**:

1. **Given** API credentials are configured in Doppler for a gated source, **When** its CronJob runs, **Then** data is fetched, validated, and stored with correct authentication headers.
2. **Given** credentials are missing or expired, **When** the CronJob runs, **Then** the job fails with a clear authentication error message logged to `meta.batch_job_runs`.

---

### User Story 5 - Implement Medium-Impact CI Sources (Priority: P5)

As a competitive intelligence analyst, I need Journal RSS feeds, USPTO PatentsView CI, and HTA body decision monitoring so that the platform tracks new journal publications, US patent activity, and health technology assessment decisions across NICE, G-BA, HAS, and PBAC.

**Why this priority**: These sources add breadth to competitive intelligence monitoring. Journal RSS covers 15-20% of CI volume, patent monitoring tracks IP landscape, and HTA decisions inform market access strategy.

**Independent Test**: Can be tested by configuring at least one journal feed / one HTA body, triggering a fetch, and verifying structured records in raw tables.

**Acceptance Scenarios**:

1. **Given** the Journal RSS framework is implemented with configurable feed URLs, **When** feeds are added for NEJM and Lancet, **Then** new article metadata is fetched daily and stored with deduplication on DOI or article URL.
2. **Given** the HTA framework supports NICE as an initial source, **When** a weekly fetch runs with query-scoped drug/therapeutic-area terms, **Then** technology appraisal decisions matching configured terms are stored with structured fields for drug name, indication, decision type, and date.

---

### User Story 6 - Implement Lower-Impact CI Sources (Priority: P6)

As a competitive intelligence analyst, I need EPO OPS patent data, Cochrane systematic reviews, medical news aggregation, and SEC EDGAR pharmaceutical filings so that the platform provides comprehensive competitive intelligence across European patents, evidence-based reviews, industry news, and financial signals.

**Why this priority**: These sources complete the CI monitoring suite but individually contribute smaller volumes (1-15% each). They are lower priority because the P3 and P5 sources already cover the majority of CI needs.

**Independent Test**: Can be tested per-source by triggering the fetcher and verifying records land in raw tables.

**Acceptance Scenarios**:

1. **Given** the SEC EDGAR fetcher is implemented, **When** a daily fetch runs for pharma companies, **Then** 10-K, 10-Q, and 8-K filing metadata is stored with deduplication on accession number.
2. **Given** the Cochrane fetcher is implemented, **When** a monthly fetch runs, **Then** systematic review metadata with drug comparisons and endpoints is stored.

---

### User Story 7 - Fix Broken ACC TVC Source (Priority: P7)

As a TAVR market analyst, I need the ACC Transcatheter Valve Certification data source restored or replaced so that hospital certification status is available for TAVR competitive analysis.

**Why this priority**: This is an existing broken source rather than a new capability. The data was previously available and analysts may have workarounds. Fixing it requires research into the new ACC data access method, which may not yield results.

**Independent Test**: Can be tested by running the updated fetcher and verifying hospital certification records appear in the `raw.acc_tvc` table.

**Acceptance Scenarios**:

1. **Given** the ACC has a new data access method, **When** the updated fetcher runs, **Then** hospital TVC certification records are fetched and stored with deduplication on facility ID.
2. **Given** no automated data access is available from ACC, **When** manual CSV upload is configured, **Then** analysts can upload TVC data through a defined process and records are loaded into the raw table.

---

### Edge Cases

- What happens when an upstream API changes its response schema between fetches? The loader should log validation errors via Pydantic but continue processing valid records, recording the error count.
- How does the system handle a source that returns zero records on a fetch? The job should succeed but log a warning, and the health check should flag the source as potentially stale.
- What happens when two CronJobs for different sources run concurrently and both need database writes? Each source writes to its own raw table, so concurrent writes should not conflict.
- How does the system handle rate limiting from upstream APIs? Fetchers must respect rate limits using retry-after headers and exponential backoff, logging rate limit events.
- What happens when Doppler secrets are not synced and a credentialed source's CronJob runs? The job should fail fast with a clear "missing credential" error rather than making unauthenticated requests.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide CronJob scheduling for each enabled data source — Tier 4 CI sources get individual CronJob manifests; Tier 2A/3 molecule sources MUST be added to existing grouped CronJobs (`mol-fetch-weekly`, `mol-fetch-monthly`) consistent with the established molecule pipeline pattern.
- **FR-002**: System MUST register each new source in `meta.data_sources` via seed SQL with source name, type, URL, description, refresh frequency, and active status.
- **FR-003**: System MUST register each new CronJob in `meta.batch_jobs` via seed SQL with job name, cron schedule, linked source IDs, and enabled status.
- **FR-004**: System MUST provide catalog metadata for each source in `catalog_refresh.py` including topic tags, AI description, column descriptions, staleness threshold, and target tables.
- **FR-005**: Each fetcher MUST use idempotent upserts (ON CONFLICT) so that re-running a fetch does not create duplicate records.
- **FR-006**: Each raw table MUST include audit columns (`_loaded_at`, `_source_file`, `_source_hash`) and a UNIQUE constraint for deduplication.
- **FR-007**: System MUST support two ingestion paths — `BaseFetcher` for TAVR/Hospital sources via `fetch_data.py` and `RawIngestionService` for molecule sources via `fetch_molecules.py`.
- **FR-008**: Credentialed sources MUST read API keys from environment variables sourced via Doppler, never hardcoded values.
- **FR-009**: Each new CronJob MUST be scheduled at a time slot that does not conflict with existing jobs (reference the CronJob schedule map).
- **FR-010**: Tier 4 CI sources MUST expose data through PostgREST API views with SELECT grants to both `web_anon` and `analyst` roles. Tier 2A/3 molecule sources defer API view creation to the SQLMesh gold-level transform pipeline (separate feature).
- **FR-011**: Competitive intelligence sources (Tier 4) MUST implement full fetcher classes inheriting from `BaseFetcher` with `fetch()` and `get_latest_url()` methods.
- **FR-012**: Each new source MUST have Pydantic validation models for data normalization and quality enforcement.
- **FR-013**: Each new source MUST have unit tests covering fetcher initialization, URL generation, mocked HTTP responses, and validator edge cases.
- **FR-014**: System MUST add each new CronJob to `k8s/base/kustomization.yaml` so that ArgoCD deploys it automatically.
- **FR-015**: CI sources MUST use a hybrid fetch strategy — high-priority sources (PubMed, OpenAlex) use broad daily ingest of all recent pharma-relevant content, while lower-priority CI sources use query-scoped fetches driven by configurable drug/therapeutic-area search terms stored in the database.

### Key Entities

- **Data Source**: Represents an external data provider with attributes: source name, type (api/csv/scrape), base URL, auth method, refresh frequency, record count, and health status. Related to one or more CronJobs.
- **CronJob**: A scheduled Kubernetes job that fetches data from a source. Attributes: job name, cron schedule, timeout, resource limits, environment variables. Each CronJob targets one or more data sources.
- **Raw Table**: The landing zone for unmodified source data. Each source has exactly one raw table in the `raw.*` or `mol_raw.*` schema with audit columns and a deduplication constraint.
- **Catalog Entry**: Metadata about a source in `meta.data_sources` including topic tags, AI description, column descriptions, staleness threshold, and target tables. Used by the catalog refresh job for health monitoring.
- **Fetcher**: A Python class that handles API communication, pagination, rate limiting, and file download for a specific source. Extends either `BaseFetcher` or `RawIngestionService`.
- **Validator**: A Pydantic model that enforces data types, required fields, and normalization rules for records from a specific source.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 5 Tier 2A sources (BindingDB, Orange Book, SIDER, TDC ADMET, EMA) are active with data in their raw tables within Sprint 1.
- **SC-002**: All 8 Tier 3 sources are active and appearing in the data catalog with health status within Sprint 3.
- **SC-003**: At least 3 CI sources (PubMed, OpenAlex, EMA Regulatory) are fetching data on schedule with deduplication working correctly within Sprint 2.
- **SC-004**: 100% of new data sources have seed SQL entries, catalog metadata, and unit tests before deployment.
- **SC-005**: Zero CronJob schedule conflicts — all new jobs run in unique time slots without overlapping existing schedules.
- **SC-006**: All new sources achieve "healthy" status in the catalog health check within 24 hours of initial deployment.
- **SC-007**: All Tier 4 CI source API views are accessible via PostgREST with correct role-based access (web_anon for public, analyst for authenticated). Molecule source views are deferred to SQLMesh.
- **SC-008**: Total platform data source count increases from 11 active to at least 24 active sources (Tiers 2A + 3 + partial Tier 4A).

## Scope

### In Scope

- Tier 2A: Enable 5 no-blocker molecule sources (CronJobs, seed SQL, catalog metadata)
- Tier 3: Enable 8 additional molecule sources (CronJobs, seed SQL, catalog metadata)
- Tier 4A: Full implementation of 3 high-impact CI sources (PubMed, OpenAlex CI, EMA Regulatory CI)
- Tier 2B: Implementation for 4 credential-gated sources (ready to deploy when credentials obtained)
- Tier 4B: Full implementation of 3 medium-impact CI sources (Journal RSS, USPTO CI, HTA)
- Tier 4C: Full implementation of 4 lower-impact CI sources (EPO, Cochrane, News, SEC EDGAR)
- Fix for broken ACC TVC source
- All associated CronJob manifests, seed SQL, catalog metadata, Pydantic validators, and tests

### Out of Scope

- Tier 5 ML/Computed sources (ESM-2, Chemprop, PubMedBERT, ADMET-AI, DTI, Formulation) — require ML infrastructure
- SQLMesh transformation models (bronze → silver → gold) — separate feature
- Admin App UI for managing data sources — separate feature (006)
- Procurement of commercial licenses (DrugBank) or OAuth app registrations (ORCID) — external process
- Changes to the `RawIngestionService` base class or molecule ingestion architecture
- PostgREST configuration changes beyond adding view grants

## Dependencies

- Doppler project `dk-data-fe` must be accessible for adding new secrets (Tier 2B and 4 sources)
- Production PostgreSQL cluster must be available for running SQL migrations
- ArgoCD must be syncing the dk-data-prod application for CronJob deployment
- NCBI API key must be obtained for PubMed (Tier 4A) — free but requires registration
- Existing `mol-fetch-daily` and `mol-fetch-weekly` CronJobs must be operational (Tier 1 verification)
- `catalog-refresh` CronJob must be working (fixed in 010-platform-stabilization)

## Assumptions

- The existing `RawIngestionService` classes in `raw_ingestion.py` are functional and only need scheduling infrastructure (CronJobs + seed SQL) to become active.
- Upstream APIs referenced in the roadmap are currently available and responding (except ACC TVC which is known broken).
- The `mol_raw` schema and related molecule schemas already exist in the production database.
- CronJob time slots 11-15 UTC are available for new sources without conflicting with other cluster workloads.
- Free-tier API rate limits are sufficient for the expected data volumes of each source.
- The `/add-datasource` skill will be used for individual source implementation, making each source a self-contained unit of work.

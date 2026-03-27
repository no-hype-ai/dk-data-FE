# Feature Specification: CMS PUF & Platform Data Reconciliation

**Feature Branch**: `019-cms-puf-platform-reconciliation`
**Created**: 2026-03-27
**Status**: Draft
**Issue**: [dk-data-FE#144](https://github.com/data-kinetic/dk-data-FE/issues/144)

## Overview

The data platform needs to absorb several bodies of work that were developed on isolation branches (016, 017) and never merged to main due to architectural drift. This feature reconciles those data sources against the canonical main-branch ingestion architecture, expands the medallion pipeline with additional regulatory and clinical sources, and improves pipeline visibility — all delivered in a single, clean integration against the current codebase.

The outcome: a significantly broader data platform that analysts can query for drug market intelligence, regulatory decisions, clinical evidence, and competitive financial intelligence — all running reliably on a scheduled basis with full refresh-history audit trails.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — CMS Public Use File Data Available for Drug Market Analysis (Priority: P1)

A data analyst needs to understand Medicare drug pricing, hospital costs, and physician prescribing patterns for competitive and market research. Today, this data cannot be queried from the platform — CMS Public Use Files were partially implemented in a branch that was never integrated.

**Why this priority**: CMS PUF data is foundational to drug market analysis. Without it, analysts must manually download and wrangle government datasets. This is the core deliverable of the 016 branch and the primary motivation for this feature.

**Independent Test**: Run a scheduled refresh cycle, verify CMS data appears in the platform data store, and confirm a downstream analyst query returns drug pricing records across multiple providers and dates.

**Acceptance Scenarios**:

1. **Given** the ingestion pipeline is running, **When** a CMS PUF refresh job executes, **Then** Medicare Part D drug pricing records, hospital cost reports, and physician data records are available for query with no manual intervention
2. **Given** a CMS data file has already been ingested in a prior run, **When** the same file is presented to the refresh job again, **Then** the job detects the file has not changed (via content hash), skips ingestion, and logs the skip — no duplicate records are created
3. **Given** a CMS upstream source is temporarily unavailable, **When** the refresh job runs, **Then** the job logs the failure into the platform refresh log, existing records are preserved, and the next scheduled run retries without human action
4. **Given** CMS data has been ingested to raw, **When** the silver-layer transformation runs, **Then** normalized records are available with consistent drug names, provider identifiers, and date fields joinable across CMS sub-programs (Part B, Part D, hospital, physician)

---

### User Story 2 — Expanded Regulatory and Clinical Evidence Sources (Priority: P2)

An analyst researching a drug's regulatory and clinical history needs data from EMA (European regulatory decisions), Cochrane (systematic review evidence), EuropePMC (literature), DrugBank (pharmacological profiles), NIH Reporter (funded research), and PubChem (compound identifiers). Today, the platform has gaps across all of these sources.

**Why this priority**: Drug market analysis without European regulatory data and clinical evidence is incomplete. These sources were planned in the 016/017 branches and documented in the issue. They follow the same ingestion architecture and can ship together.

**Independent Test**: Verify at least one new source (e.g., EMA regulatory decisions) can be refreshed independently and queried. Each additional source can be enabled and tested independently once the shared infrastructure is in place.

**Acceptance Scenarios**:

1. **Given** the platform is running, **When** a regulatory data refresh runs, **Then** EMA drug decision records (approvals, refusals, withdrawals) are available with agency, drug name, decision date, and indication fields
2. **Given** a drug name is known, **When** the platform is queried, **Then** cross-source data (EMA regulatory status, Cochrane systematic review existence, EuropePMC publication count, NIH funding history) can be joined on a common drug identifier
3. **Given** a new drug compound is approved, **When** ingestion runs, **Then** the compound appears in the platform within the next scheduled refresh cycle with PubChem identifiers linked to regulatory records
4. **Given** DrugBank data has been ingested, **When** silver transformation runs, **Then** pharmacological classification, mechanism of action, and indication data are normalized and queryable alongside market data

---

### User Story 3 — Full Refresh History Visible in Platform Audit Log (Priority: P3)

An operations engineer monitoring the data platform needs to inspect the history of every source refresh: when it ran, how many records were processed, whether it succeeded or partially failed, and how long it took. Today, new sources added from the 016 branch have no entries in the platform's refresh log because they were never registered in the source registry.

**Why this priority**: Without refresh history, stale data looks current, failures are invisible, and there is no basis for scheduling decisions. The platform already has the `meta.data_sources` and `meta.refresh_log` infrastructure — new sources just need to be registered and their runs logged correctly.

**Independent Test**: After a CMS refresh completes, query `meta.refresh_log` and confirm an entry exists with source name, start/end timestamp, records inserted, and status. Query `meta.data_sources` and confirm `last_successful_refresh` is updated.

**Acceptance Scenarios**:

1. **Given** any new source completes a refresh (success or failure), **When** `meta.refresh_log` is queried, **Then** an entry exists with: source name, start timestamp, end timestamp, records fetched, records inserted, records updated, and error details if applicable
2. **Given** a source has run at least once successfully, **When** the platform schedules the next refresh, **Then** the incremental lookback window is computed from `last_successful_refresh` plus a one-day safety overlap — not a fixed hardcoded window
3. **Given** a source has never been run, **When** the refresh job runs for the first time, **Then** the job uses the configured default lookback period (e.g., 90 days for regulatory sources, 365 days for CMS annual files) and logs the run as initial backfill
4. **Given** a source run fails partway through, **When** `meta.data_sources` is queried, **Then** `last_refresh_status` reflects 'failed' or 'partial' and `last_successful_refresh` is NOT updated to the failed run's timestamp

---

### User Story 4 — LLM-Enriched Provider Intelligence via Agent System (Priority: P4)

Raw CMS ingestion gives you facts — provider names, NPI codes, DRG claims. But a clinical sales analyst needs richer intelligence: which clinical service lines does a hospital run, who owns which IDN, which facilities are likely referring patients to whom. This inference cannot be read directly from the data — it requires reasoning over partial information.

**Why this priority**: The agent system is the highest-value differentiation of the CMS data layer. Without it the platform is a data warehouse. With it, it is an intelligence platform. Lower than CMS and regulatory sourcing because those are prerequisites.

**Independent Test**: Trigger the service line inference agent for a single hospital (by NPI), verify a service line record is written to the silver layer with a confidence score, and confirm that records below the confidence threshold appear in the quarantine table rather than in the live silver view.

**Acceptance Scenarios**:

1. **Given** a hospital's DRG claims data is ingested, **When** the service line inference agent runs, **Then** clinical service line assignments are written to the silver layer with a confidence score per record
2. **Given** a publication abstract is available in the platform, **When** the publication evidence extraction agent runs, **Then** structured clinical endpoints (hazard ratio, p-value, response rate, median survival, sample size) are extracted and written to `mol_silver.publication_evidence` — making them available in `mol_gold.trial_outcomes` without any dependency on the Xenon system
3. **Given** an agent produces a result with confidence below 0.5, **When** the result is processed, **Then** the record is written to the quarantine table for manual review and does NOT appear in the live silver view
4. **Given** an agent produces a result with confidence between 0.5 and 0.79, **When** the result is written, **Then** the record appears in the silver layer with a `needs_review` flag, visible to analysts but marked for validation
5. **Given** agents run on their monthly schedule, **When** a run completes, **Then** the refresh log contains an entry for each agent with record counts, confidence distribution, and quarantine count

---

### User Story 5 — On-Demand Data Backfill via Data Tools Gateway (Priority: P5)

An analyst queries a gold-layer drug view and gets no results because a source has not been ingested for that compound yet. Today there is no self-service way to trigger a targeted refresh — the analyst must wait for the next scheduled run. The data tools gateway gives agents and analysts a way to request a backfill for a specific source on demand.

**Why this priority**: Unblocks analysts and agents from waiting for scheduled cycles. Depends on CMS and regulatory ingestion working first.

**Independent Test**: Call the backfill endpoint for a single CMS source, verify records appear in the corresponding gold view shortly after, and confirm `meta.refresh_log` has an entry for the triggered run.

**Acceptance Scenarios**:

1. **Given** a gold-layer view returns empty results for a source, **When** a backfill is requested for that source, **Then** the platform fetches fresh upstream data, runs the silver/gold transformation, and the view returns records within the current session
2. **Given** local data for a source already exists and is sufficiently fresh, **When** a backfill is requested, **Then** the gateway checks the local DB first and skips the external fetch
3. **Given** the tool registry is queried, **When** all available tools are listed, **Then** all sources are returned with their category, supported query parameters, and last-refresh metadata

---

### User Story 6 — SEC EDGAR 10-K/20-F Filing Intelligence (Priority: P6)

A competitive intelligence analyst needs to extract structured data from pharmaceutical company 10-K annual reports and 20-F foreign filings — specifically revenue by drug, pipeline stage disclosures, and risk factor language — to track competitive positioning over time.

**Why this priority**: SEC EDGAR is the authoritative source for public company financial disclosures. This is lower priority than operational CMS/regulatory data but represents significant long-term platform value for competitive analysis. Scoped to full document retrieval and normalized storage; structured extraction is a downstream concern.

**Independent Test**: Trigger a refresh for a single tracked company (e.g., Pfizer), verify the most recent 10-K filing text is stored and queryable, and confirm the run appears in `meta.refresh_log` with the expected record count.

**Acceptance Scenarios**:

1. **Given** a pharmaceutical company's CIK (EDGAR company identifier) is registered, **When** the EDGAR refresh runs, **Then** the most recent annual filing (10-K or 20-F) is fetched and stored with filing date, company name, document type, and full text available for query
2. **Given** a company has filed multiple annual reports, **When** the platform is queried, **Then** filings from the current and prior two fiscal years are available, with newer filings not overwriting older ones
3. **Given** an EDGAR source run completes, **When** silver transformation runs, **Then** normalized records include: company ticker, CIK, fiscal year end, filing date, and whether the document contains drug-specific revenue disclosures (binary flag from keyword detection)

---

### Edge Cases

- What happens when a CMS PUF file URL changes between refresh cycles (government dataset URL instability)?
- What happens when a source returns a valid response but with zero records (empty dataset from upstream)?
- What happens when two CMS sub-programs reference the same drug using different naming conventions — which name is authoritative in the silver layer?
- What happens when an SEC filing is very large and parsing takes longer than the scheduled run window?
- What happens when a destructive database migration is applied against a database that has not been backed up?
- What happens when `meta.data_sources` does not contain an entry for a source — will the run proceed or fail?

---

## Requirements *(mandatory)*

### Functional Requirements

**Data Ingestion — CMS Public Use Files**

- **FR-001**: The platform MUST ingest data from the complete set of CMS PUF programs: Medicare Part B drug spending, Part D drug spending, hospital cost reports, physician and other supplier data, and related HCS sub-programs (31 sources total)
- **FR-002**: Each new CMS source MUST be registered in `meta.data_sources` with: source name, source type, description, refresh frequency, and default lookback period — registration is required before any CronJob is deployed
- **FR-003**: For CMS file-based sources, the pipeline MUST compute a content hash of the downloaded file and check whether that hash already exists in the raw table before inserting — if the file has not changed, ingestion is skipped and the skip is logged
- **FR-004**: CMS raw records MUST follow the existing direct-normalized raw table pattern used by other CMS sources on main: a stable document identifier, ingestion timestamp (`_loaded_at`), content hash (`_source_hash`), and source file provenance — NOT the JSONB medallion pattern
- **FR-005**: The silver layer MUST normalize CMS records into a unified drug-provider-cost schema joinable across Part B, Part D, and hospital programs using standardized drug identifiers and NPI provider codes

**Data Ingestion — Regulatory and Clinical Sources**

- **FR-006**: The platform MUST ingest EMA regulatory decisions (drug approvals, refusals, and withdrawals) with European-specific fields: CHMP opinion date, indication, therapeutic area, and orphan designation status
- **FR-007**: The platform MUST ingest Cochrane systematic review metadata (title, PICO population/intervention, review date, conclusion summary) for drugs tracked by the platform
- **FR-008**: The platform MUST ingest EuropePMC literature citations with drug mention extraction linked to known drug identifiers
- **FR-009**: The platform MUST ingest DrugBank pharmacological profiles including drug classification, mechanism of action, indication, and cross-referencing to PubChem compound IDs
- **FR-010**: The platform MUST ingest NIH Reporter funded research grants with principal investigator, institution, project title, and associated drug/disease terms
- **FR-011**: The platform MUST ingest PubChem compound records to maintain a canonical compound identifier map linking brand names, generic names, and chemical identifiers used by other sources
- **FR-012**: The silver layer MUST produce a `market_summary` view joining pricing trends (CMS), regulatory status (FDA/EMA), clinical evidence volume (Cochrane/EuropePMC), and pipeline activity (NIH) for each tracked drug — and MUST degrade gracefully if any single source is absent

**Pipeline State Tracking (using existing infrastructure)**

- **FR-013**: Every new source MUST call `log_to_meta(source_name, result)` after each run, where result is the loader's output dict containing: `status`, `records_fetched`, `records_inserted`, `records_updated`, and `errors` — this writes to both `meta.refresh_log` and updates `meta.data_sources`
- **FR-014**: Every new source with a date-windowed fetch (API sources) MUST use `_compute_days_back(source, source_info)` to determine its lookback window — the lookback is derived from `last_successful_refresh` in `meta.data_sources`, not hardcoded
- **FR-015**: Every new source MUST be present in the central `SOURCES` registry dict with: `fetcher` class, `loader` callable, `requires_file` flag, and `default_days_back` (or `None` for non-incremental sources)
- **FR-016**: Every new fetcher MUST return a dict matching the canonical shape: `{status: 'success'|'failed', records: List[Dict], hash: str|None}` — loaders MUST return `{status, records_inserted, records_updated, errors: List[str]}`

**SEC EDGAR**

- **FR-017**: The platform MUST fetch the most recent 10-K and 20-F annual filings from SEC EDGAR for a configured list of pharmaceutical companies, identified by CIK
- **FR-018**: EDGAR filing records MUST store: CIK, company name, ticker, filing type, fiscal year end date, filing date, accession number, and full document text
- **FR-019**: A silver-layer transformation MUST flag filings that contain drug-specific revenue disclosures (detected via keyword presence) to support downstream prioritization

**Agent System**

- **FR-024**: The platform MUST include 7 enrichment agents: 6 domain-specific CMS agents (service line inference, IDN hierarchy, referral network, contact verification, staffing decomposition, equipment inventory) plus a publication evidence extraction agent that reads publication abstracts from the silver layer and writes structured clinical endpoints to `mol_silver.publication_evidence`
- **FR-024a**: The publication evidence extraction agent MUST eliminate the dependency on the `xenon` schema — `mol_gold.trial_outcomes` MUST read from `mol_silver.publication_evidence` (not `xenon.publication_evidence`). The `xenon` schema is retained for the Xenon application's own use but removed from dk-data-FE's PostgREST exposure
- **FR-025**: Every agent MUST route all LLM calls through the shared LiteLLM proxy — no direct API calls to any LLM provider
- **FR-026**: Records produced with confidence below 0.5 MUST be written to a quarantine table and excluded from live silver views until manually reviewed and resolved
- **FR-027**: Records produced with confidence between 0.5 and 0.79 MUST be written to the silver layer with a `needs_review` flag set to TRUE
- **FR-028**: Agents MUST be triggerable both on a monthly scheduled basis and on demand via API — a single agent run MUST NOT require a full pipeline restart

**Data Tools Gateway**

- **FR-029**: The platform MUST expose a tool registry listing all available data sources (CMS and molecule) with metadata: category, supported query keys, and last-refresh timestamp
- **FR-030**: For any registered source, the platform MUST provide a backfill endpoint that fetches fresh upstream data and runs the silver/gold transformation without manual intervention
- **FR-031**: Before triggering an external fetch, the gateway MUST check local data freshness and skip the external call if sufficiently recent data exists

**Clinical Evidence Silver Layer**

- **FR-032**: The platform MUST maintain a `mol_silver.publication_evidence` table storing LLM-extracted clinical endpoints (hazard ratio, p-value, response rate, median survival, sample size) deduplicated by content hash, with `confidence_score` and `needs_review` columns
- **FR-033**: `mol_gold.trial_outcomes` MUST UNION `mol_silver.clinical_trials` (registry-sourced, confidence = 1.0) with `mol_silver.publication_evidence` (LLM-extracted, confidence ≥ 0.40) — no reference to the `xenon` schema

**Data Integrity and Migration**

- **FR-020**: All schema changes MUST be delivered as a single consolidated migration script that can be reviewed, tested, and rolled back as a unit — no split migrations across the PR
- **FR-021**: The migration MUST reflect only the delta from the current main-branch schema — not a replay of 016 branch migrations, which reference dropped schemas and renamed columns that no longer apply
- **FR-022**: Any migration step that drops or renames columns or schemas MUST be preceded by a documented pre-flight check confirming: production backup taken, no active queries on affected schema, rollback script available
- **FR-023**: All existing tests MUST pass after the migration is applied — zero regressions in previously working data sources

### Key Entities

- **DataSource**: A registered entry in `meta.data_sources` with a unique source name, refresh frequency, and default lookback. Required before any scheduled job can run
- **RunLog**: An entry in `meta.refresh_log` capturing the outcome of one source refresh — timing, record counts, status, and errors. Written by `log_to_meta()` after every run
- **RawRecord**: An immutable ingestion record for a single item from a source, stored in the source's raw table with `_loaded_at`, `_source_hash`, and source provenance. File-based sources skip insert if `_source_hash` already exists
- **SilverRecord**: A normalized business entity (drug, provider, decision, filing) derived from raw records via SQLMesh incremental transformation, updated on each transform run
- **DrugIdentifier**: A cross-source canonical drug record linking brand name, INN generic name, PubChem CID, and internal platform drug ID — the join key for multi-source queries in the silver layer
- **MarketSummary**: A gold-layer aggregate view per drug combining pricing trend, regulatory status, evidence volume, and funding activity — built from silver records, degrades gracefully when sources are absent
- **AgentRecord**: An enriched inference result produced by an LLM agent from raw CMS data, stored in the silver layer with a confidence score and `needs_review` flag
- **QuarantineRecord**: An agent result with confidence below 0.5, stored separately from live silver data pending manual review and resolution
- **DataTool**: A registered backfill-capable data source in the tool registry, with metadata describing what it can fetch and how fresh the local data is
- **PublicationEvidence**: A structured clinical endpoint record extracted from a publication abstract by the platform's own agent. Stored in `mol_silver.publication_evidence`, deduplicated by content hash, included in `mol_gold.trial_outcomes` when confidence ≥ 0.40

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 31 CMS PUF sources are registered in `meta.data_sources` and produce entries in `meta.refresh_log` after their first scheduled run — zero sources run silently without a log entry
- **SC-002**: For file-based CMS sources, a second consecutive run with no upstream file change produces zero new inserts and completes without error — confirming hash-skip works end to end
- **SC-003**: Silver-layer drug records are joinable across at least 4 distinct source categories (pricing, regulatory, clinical, compound) for 90% of drugs tracked by the platform
- **SC-004**: The consolidated migration applies cleanly to a staging database from the current main-branch schema state with zero manual intervention required
- **SC-005**: Test coverage for all new fetchers, loaders, and silver transformations meets the existing project coverage threshold — no new untested code paths introduced
- **SC-006**: All existing tests continue to pass after the migration is applied — zero regressions
- **SC-007**: After initial deployment, `meta.data_sources.last_successful_refresh` is populated for every new source within its first successful run, and subsequent runs use the computed incremental window rather than the default backfill window
- **SC-008**: EDGAR filing content for a configured pharmaceutical company list is available within the next scheduled refresh cycle after initial deployment — no manual seeding required
- **SC-009**: Agent runs produce zero direct LLM API calls — all calls route through the LiteLLM proxy, confirmed by absence of external provider credentials in agent code
- **SC-010**: After an agent monthly run, the quarantine table contains only records with confidence < 0.5, and the silver layer contains no unscored records — every agent result has a confidence value
- **SC-011**: A backfill request for any registered source completes and produces queryable gold-layer data within 10 minutes of the API call, with a corresponding entry in `meta.refresh_log`
- **SC-012**: After the publication evidence extraction agent runs, clinical endpoints are queryable in `mol_gold.trial_outcomes` with `evidence_source = 'publication'` — with no `xenon` schema reference in the query path

---

## Assumptions

- `meta.data_sources` and `meta.refresh_log` already exist on main; the migration does not need to create them — only add new source registrations
- The `hcs_raw` schema exists in the target database; the migration adds tables within it rather than creating a new schema
- Drug name normalization uses INN (International Nonproprietary Name) as the canonical identifier; brand names are stored as aliases
- The existing CronJob infrastructure (OTEL telemetry, read-only root filesystem, standard env vars) requires no changes — only new job manifest files are added
- CMS file-based sources use the existing hash-skip pattern already implemented for `cms_medicare_inpatient` and similar sources — no new skip logic needs to be built
- SEC EDGAR coverage begins with a curated list of 20–30 major pharmaceutical companies; expansion to a broader universe is a separate follow-on feature
- The destructive migrations from the 016 branch (schema DROP, column renames, column drops) must be audited against current main-branch schema before the consolidated migration is written — the PR migration will only reflect the actual delta from current main state

## Out of Scope for This PR

- Structured revenue/pipeline extraction from SEC filings beyond keyword flagging — full NLP parsing is a downstream feature
- Expansion of EDGAR coverage beyond the initial curated list of pharmaceutical companies
- Reading from the `xenon` schema in dk-data-FE — publication evidence is owned and extracted by the platform's own agent
- Uplift/sync of monitoring config to dk-alchemy — tracked separately in dk-data-FE#145

## Implementation Order

Each piece can be independently tested and merged if needed:

1. **Consolidated migration** — audit all 57 016 migrations against current main schema; write the delta-only consolidated script; apply to staging; verify existing tests pass
2. **CMS PUF fetchers and loaders** (P1) — 28 sources using existing file-based hash-skip pattern; register all in `meta.data_sources` and `SOURCES` dict
3. **Regulatory and clinical sources** (P2) — EMA first, then Cochrane, EuropePMC, DrugBank, NIH Reporter, PubChem; each logged via `log_to_meta()`
4. **Market summary silver view** — after CMS and EMA are verified
5. **Agent system** (P4) — port 7 agent files (6 CMS domain agents + publication evidence extractor) + quarantine table + agents API router + CronJob + K8s Job template
6. **Data tools gateway** (P5) — port 27 service files + data_tools API router + data_registry.py
7. **`mol_silver.publication_evidence`** — new silver table + SQLMesh INCREMENTAL model; restore `mol_gold.trial_outcomes` reading from silver; remove `xenon` from PostgREST schema list
8. **SQLMesh scheduler with advisory lock** — deadlock prevention deployment
9. **SEC EDGAR** (P6) — independent of other sources; can ship in this PR or a follow-on

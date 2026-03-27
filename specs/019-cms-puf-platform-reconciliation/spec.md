# Feature Specification: CMS PUF & Platform Data Reconciliation

**Feature Branch**: `019-cms-puf-platform-reconciliation`
**Created**: 2026-03-27
**Status**: Draft
**Issue**: [dk-data-FE#144](https://github.com/data-kinetic/dk-data-FE/issues/144)

## Overview

The data platform needs to absorb several bodies of work that were developed on isolation branches (016, 017) and never merged to main due to architectural drift. This feature reconciles those data sources against the canonical main-branch ingestion architecture, expands the medallion pipeline with additional regulatory and clinical sources, and introduces pipeline efficiency improvements — all delivered in a single, clean integration against the current codebase.

The outcome: a significantly broader data platform that analysts can query for drug market intelligence, regulatory decisions, clinical evidence, and competitive financial intelligence — all running reliably on a scheduled basis.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — CMS Public Use File Data Available for Drug Market Analysis (Priority: P1)

A data analyst needs to understand Medicare drug pricing, hospital costs, and physician prescribing patterns for competitive and market research. Today, this data cannot be queried from the platform — CMS Public Use Files were partially implemented in a branch that was never integrated.

**Why this priority**: CMS PUF data is foundational to drug market analysis. Without it, analysts must manually download and wrangle government datasets. This is the core deliverable of the 016 branch and the primary motivation for this feature.

**Independent Test**: Run a scheduled refresh cycle, verify CMS data appears in the platform data store, and confirm a downstream analyst query returns drug pricing records across multiple providers and dates.

**Acceptance Scenarios**:

1. **Given** the ingestion pipeline is running, **When** a CMS PUF refresh job executes, **Then** Medicare Part D drug pricing records, hospital cost reports, and physician data records are available for query with no manual intervention
2. **Given** the platform has previously ingested CMS data, **When** the refresh job runs again with no upstream changes, **Then** no duplicate records are created and the run completes in significantly less time than a full fetch
3. **Given** a CMS upstream source is temporarily unavailable, **When** the refresh job runs, **Then** the job logs the failure gracefully, existing records are preserved, and the next scheduled run retries without human action
4. **Given** CMS data has been ingested to raw, **When** the silver-layer transformation runs, **Then** normalized records are available with consistent drug names, provider identifiers, and date fields joined across CMS sub-programs (Part B, Part D, hospital, physician)

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

### User Story 3 — Pipeline Reliability: No Redundant Fetches, No Silent Failures (Priority: P3)

An operations engineer monitoring the data platform needs confidence that scheduled jobs are not re-downloading data that hasn't changed, are not silently failing, and are picking up where they left off after partial failures.

**Why this priority**: Without idempotency and checkpoint support, large fetches (CMS files can be hundreds of MB) re-run from scratch every cycle, wasting network and compute. Silent failures mean stale data that analysts treat as current. This unlocks reliable daily scheduling.

**Independent Test**: Run a full fetch, then immediately run again. Verify the second run fetches zero records from sources that haven't changed (hash-skip), and that job run metadata is logged with timing and record counts.

**Acceptance Scenarios**:

1. **Given** a source has already been fetched and the upstream data has not changed, **When** the refresh job runs, **Then** the source is skipped after a content-hash check and the run completes in under 10 seconds for that source
2. **Given** a paginated fetch was interrupted mid-way (network error), **When** the job runs again, **Then** fetching resumes from the last successfully checkpointed page rather than restarting from page 1
3. **Given** any ingestion run completes (success or partial), **When** the meta tables are queried, **Then** a log entry exists with: source name, run timestamp, records ingested, records skipped, errors encountered, and duration
4. **Given** a source responds with a 304 Not Modified (conditional HTTP), **When** the job processes it, **Then** no fetch body is downloaded and the run is logged as "no new data"

---

### User Story 4 — SEC EDGAR 10-K/20-F Filing Intelligence (Priority: P4)

A competitive intelligence analyst needs to extract structured data from pharmaceutical company 10-K annual reports and 20-F foreign filings — specifically revenue by drug, pipeline stage disclosures, and risk factor language — to track competitive positioning over time.

**Why this priority**: SEC EDGAR is the authoritative source for public company financial disclosures. This is lower priority than operational CMS/regulatory data but represents significant long-term platform value for competitive analysis. Scoped to full document retrieval and normalized storage; structured extraction is a downstream concern.

**Independent Test**: Trigger a refresh for a single tracked company (e.g., Pfizer), verify the most recent 10-K filing text is stored and queryable, and confirm no personally identifiable information or copyrighted content is retained beyond what EDGAR publicly provides.

**Acceptance Scenarios**:

1. **Given** a pharmaceutical company's CIK (EDGAR company identifier) is configured, **When** the EDGAR refresh runs, **Then** the most recent annual filing (10-K or 20-F) is fetched and stored with filing date, company name, document type, and full text available for query
2. **Given** a company has filed multiple annual reports, **When** the platform is queried, **Then** filings from the current and prior two fiscal years are available, with newer filings not overwriting older ones
3. **Given** an EDGAR source is fetched, **When** silver transformation runs, **Then** normalized records include: company ticker, CIK, fiscal year end, filing date, and whether the document contains drug-specific revenue disclosures (binary flag from keyword detection)

---

### Edge Cases

- What happens when a CMS PUF file URL changes between refresh cycles (government dataset URL instability)?
- How does the pipeline handle a source that returns a valid response but with zero records (empty dataset from upstream)?
- What happens when two CMS sub-programs reference the same drug using different naming conventions — which name is authoritative in the silver layer?
- How does the system behave when an SEC filing is very large (>100MB) and parsing times out?
- What happens when a destructive database migration (schema change) is applied against a production database that has not been fully backed up?

---

## Requirements *(mandatory)*

### Functional Requirements

**Data Ingestion — CMS Public Use Files**

- **FR-001**: The platform MUST ingest data from the complete set of CMS PUF programs: Medicare Part B drug spending, Part D drug spending, hospital cost reports, physician and other supplier data, and related HCS sub-programs (31 sources total)
- **FR-002**: Each CMS source MUST be registered in the central source registry with a defined refresh cadence, a flag indicating whether it requires a pre-downloaded file or fetches directly, and a configurable lookback period
- **FR-003**: CMS raw records MUST be stored with a stable identifier, ingestion timestamp, content hash, and source provenance — enabling duplicate detection and incremental refresh
- **FR-004**: The silver layer MUST normalize CMS records into a unified drug-provider-cost schema joinable across Part B, Part D, and hospital programs using standardized drug identifiers and NPI provider codes

**Data Ingestion — Regulatory and Clinical Sources**

- **FR-005**: The platform MUST ingest EMA regulatory decisions (drug approvals, refusals, and withdrawals) with European-specific fields: CHMP opinion date, indication, therapeutic area, and orphan designation status
- **FR-006**: The platform MUST ingest Cochrane systematic review metadata (title, PICO population/intervention, review date, conclusion summary) for drugs tracked by the platform
- **FR-007**: The platform MUST ingest EuropePMC literature citations with drug mention extraction linked to known drug identifiers
- **FR-008**: The platform MUST ingest DrugBank pharmacological profiles including drug classification, mechanism of action, indication, and cross-referencing to PubChem compound IDs
- **FR-009**: The platform MUST ingest NIH Reporter funded research grants with principal investigator, institution, project title, and associated drug/disease terms
- **FR-010**: The platform MUST ingest PubChem compound records to maintain a canonical compound identifier map linking brand names, generic names, and chemical identifiers used by other sources
- **FR-011**: The silver layer MUST produce a `market_summary` view joining pricing trends (CMS), regulatory status (FDA/EMA), clinical evidence volume (Cochrane/EuropePMC), and pipeline activity (NIH) for each tracked drug

**Pipeline Efficiency**

- **FR-012**: The ingestion pipeline MUST compute a content hash for each fetched source response and skip re-processing when the hash matches the previous successful run
- **FR-013**: For paginated sources, the pipeline MUST checkpoint progress after each page and resume from the last checkpoint on retry, not from the beginning
- **FR-014**: For sources that support conditional HTTP (ETag/Last-Modified), the pipeline MUST send conditional request headers and treat a 304 response as a no-op run
- **FR-015**: Every ingestion run MUST write a structured log entry to the platform meta tables including: source name, start time, end time, records ingested, records skipped (hash match), and any errors encountered

**SEC EDGAR**

- **FR-016**: The platform MUST fetch the most recent 10-K and 20-F annual filings from SEC EDGAR for a configured list of pharmaceutical companies, identified by CIK
- **FR-017**: EDGAR filing records MUST store: CIK, company name, ticker, filing type, fiscal year end date, filing date, accession number, and full document text
- **FR-018**: A silver-layer transformation MUST flag filings that contain drug-specific revenue disclosures (detected via keyword presence) to support downstream prioritization

**Data Integrity and Migration**

- **FR-019**: All schema changes MUST be delivered as a single consolidated migration script that can be reviewed, tested, and rolled back as a unit — no split migrations across the PR
- **FR-020**: Any migration that drops or renames columns or schemas MUST include a pre-flight checklist confirming: production backup taken, no active queries dependent on the affected schema, rollback script available
- **FR-021**: The platform MUST pass all existing tests after schema changes — no regressions in previously working data sources

### Key Entities

- **DataSource**: A registered external data provider with a unique key, refresh cadence, lookback period, and file-vs-fetch mode. Examples: `cms_part_d_drug_spending`, `ema_regulatory_decisions`, `sec_edgar_10k`
- **RawRecord**: An immutable ingestion artifact for a single record from a source, identified by a stable document ID and a content hash. Written once; never updated
- **SilverRecord**: A normalized, deduplicated business entity (drug, provider, decision, filing) derived from one or more raw records, updated incrementally on each transform run
- **RunLog**: A metadata record capturing the outcome of a single source refresh execution — timing, counts, status, and errors — used for operational monitoring and debugging
- **DrugIdentifier**: A cross-source canonical drug record linking brand name, generic name (INN), PubChem CID, and internal platform drug ID — the join key for multi-source queries
- **MarketSummary**: A gold-layer aggregate view per drug combining pricing trend, regulatory status, evidence volume, and funding activity, updated on each full refresh cycle

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 31 CMS PUF sources successfully refresh on their scheduled cadence for 4 consecutive weeks without manual intervention, measured by absence of failed run log entries
- **SC-002**: A second consecutive run of any source that returned data in the prior run completes in under 30 seconds (hash-skip path), compared to typical full-fetch time of multiple minutes
- **SC-003**: Silver-layer drug records are joinable across at least 4 distinct source categories (pricing, regulatory, clinical, compound) for 90% of drugs tracked by the platform
- **SC-004**: The consolidated migration applies cleanly to a staging database from a clean main-branch state with zero manual intervention required
- **SC-005**: Test coverage for all new fetchers, loaders, and silver transformations meets the existing project coverage threshold — no new untested code paths
- **SC-006**: All existing tests continue to pass after the migration is applied — zero regressions
- **SC-007**: For any source supporting conditional HTTP, a no-change run transfers zero bytes of payload data, confirmed via network logging
- **SC-008**: EDGAR filing content for a configured pharmaceutical company list is available within the next scheduled refresh cycle after initial deployment — no manual seeding required

---

## Assumptions

- The `hcs_raw` schema is already established in the target database; the migration adds tables within it rather than creating a new schema
- Drug name normalization in the silver layer uses the INN (International Nonproprietary Name) as the canonical identifier, with brand names stored as aliases
- The existing CronJob infrastructure (scheduled task runners with OTEL telemetry and read-only root filesystem) is available and does not require changes — only new job definitions are added
- The 30-day lookback default for date-windowed sources is appropriate for initial deployment; operators can adjust per-source defaults via configuration without code changes
- SEC EDGAR coverage begins with a curated list of 20–30 major pharmaceutical companies; expansion to full EDGAR pharmaceutical universe is a separate follow-on feature
- The destructive migrations (121: schema drop, 122: column renames, 129: column drops) from the 016 branch must be audited against current main-branch schema before execution — the migration delivered in this PR will reflect only the delta needed from the current main-branch schema state

## Dependencies

- All new data sources must be registered in the central source registry before CronJobs are deployed
- The `market_summary` silver view depends on at least one CMS pricing source and one regulatory source being available; it must degrade gracefully if either is absent
- SEC EDGAR full-text storage requires sufficient database storage headroom for large document payloads — operations team to confirm capacity before enabling EDGAR CronJob in production
- EMA and Cochrane sources use pagination; checkpoint infrastructure (FR-013) must be implemented before enabling these sources on their full refresh cadence

## Implementation Order

To ensure each piece can be independently tested and merged if needed:

1. **Consolidated migration** — establish all schema changes in a single reviewed script; apply to staging first
2. **CMS PUF fetchers and loaders** (P1) — the largest surface area; must pass tests before expanding
3. **Pipeline efficiency infrastructure** (P3) — hash-skip and checkpoint are shared across all new sources; implement as reusable base behavior, not per-fetcher
4. **Regulatory and clinical sources** (P2) — EMA first (most structured), then Cochrane, EuropePMC, DrugBank, NIH Reporter, PubChem
5. **Market summary silver view** — depends on CMS + at least one regulatory source being present
6. **SEC EDGAR** (P4) — independent of other sources; can ship last or in a follow-on PR

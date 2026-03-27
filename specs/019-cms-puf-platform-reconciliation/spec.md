# Feature Specification: CMS PUF & Platform Data Reconciliation

**Feature Branch**: `019-cms-puf-platform-reconciliation`
**Created**: 2026-03-27
**Status**: Draft
**Issue**: [dk-data-FE#144](https://github.com/data-kinetic/dk-data-FE/issues/144)

## Overview

The data platform needs to absorb several bodies of work that were developed on isolation branches (016, 017) and never merged to main due to architectural drift. This feature reconciles those data sources against the canonical main-branch ingestion architecture, expands the medallion pipeline with additional regulatory and clinical sources, and improves pipeline visibility — all delivered in a single, clean integration against the current codebase.

The outcome: a significantly broader data platform that analysts can query for drug market intelligence, regulatory decisions, clinical evidence, and competitive financial intelligence — all running reliably on a scheduled basis with full refresh-history audit trails.

---

## Clarifications

### Session 2026-03-27

- Q: Is the CMS PUF source count 31 (FR-001, SC-001) or 28 (blueprint, issue #144)? → A: 28 — the correct count from the 016 branch audit; FR-001 and SC-001 updated to match
- Q: Which new schemas should be exposed via PostgREST? → A: Silver and gold only for all domain namespaces — bronze is excluded (existing pattern: `mol_bronze` is not exposed, only `mol_silver` and `mol_gold`). This feature adds `hcs_silver` and `hcs_gold` to the exposure list. Raw schemas are never exposed.
- Q: Where should API rate-limit retry logic live — BaseFetcher or per-fetcher? → A: Retry-with-backoff in BaseFetcher, configurable max retries and base delay per source; all API fetchers inherit it automatically
- Q: Should the pipeline emit proactive alerts when sources fail? → A: Yes — Grafana alert rule firing when any source has ≥ 3 consecutive failed runs in meta.refresh_log; no new tooling required
- Q: How should SEC EDGAR full filing text be stored — inline column, separate table, or object storage? → A: Inline TEXT column in the raw table; PostgreSQL TOAST handles compression automatically — no separate overflow table or external storage

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

- **FR-001**: The platform MUST ingest data from the complete set of CMS PUF programs: Medicare Part B drug spending, Part D drug spending, hospital cost reports, physician and other supplier data, and related HCS sub-programs (28 sources total)
- **FR-002**: Each new CMS source MUST be registered in `meta.data_sources` with: source name, source type, description, refresh frequency, and default lookback period — registration is required before any CronJob is deployed
- **FR-003**: For CMS file-based sources, the pipeline MUST compute a content hash of the downloaded file and check whether that hash already exists in the raw table before inserting — if the file has not changed, ingestion is skipped and the skip is logged
- **FR-004**: CMS raw records MUST follow the existing direct-normalized raw table pattern used by other CMS sources on main: a stable document identifier, ingestion timestamp (`_loaded_at`), content hash (`_source_hash`), and source file provenance — NOT the JSONB medallion pattern
- **FR-005**: The silver layer MUST normalize CMS records into a unified drug-provider-cost schema joinable across Part B, Part D, and hospital programs using standardized drug identifiers and NPI provider codes

**Data Ingestion — Regulatory and Clinical Sources**

- **FR-006**: The platform MUST ingest EMA regulatory decisions (drug approvals, refusals, and withdrawals) with European-specific fields: CHMP opinion date, indication, therapeutic area, and orphan designation status
- **FR-007**: The platform MUST ingest Cochrane systematic review metadata (title, PICO population/intervention, review date, conclusion summary) for drugs tracked by the platform
- **FR-008**: The platform MUST ingest EuropePMC literature citations with drug mention extraction linked to known drug identifiers. EuropePMC records are normalized in `mol_bronze.europepmc` and then consolidated into the existing `silver.publications` model as a new CTE — they do NOT create a separate `mol_silver.europepmc` table
- **FR-009**: The platform MUST ingest DrugBank pharmacological profiles including drug classification, mechanism of action, indication, and cross-referencing to PubChem compound IDs
- **FR-010**: The platform MUST ingest NIH Reporter funded research grants with principal investigator, institution, project title, and associated drug/disease terms
- **FR-011**: The platform MUST ingest PubChem compound records to maintain a canonical compound identifier map linking brand names, generic names, and chemical identifiers used by other sources
- **FR-012**: The silver layer MUST produce a `market_summary` view joining pricing trends (CMS), regulatory status (FDA/EMA), clinical evidence volume (Cochrane/EuropePMC), and pipeline activity (NIH) for each tracked drug — and MUST degrade gracefully if any single source is absent

**Pipeline State Tracking (using existing infrastructure)**

- **FR-013**: Every new source MUST call `log_to_meta(source_name, result)` after each run, where result is the loader's output dict containing: `status`, `records_fetched`, `records_inserted`, `records_updated`, and `errors` — this writes to both `meta.refresh_log` and updates `meta.data_sources`
- **FR-014**: Every new source with a date-windowed fetch (API sources) MUST use `_compute_days_back(source, source_info)` to determine its lookback window — the lookback is derived from `last_successful_refresh` in `meta.data_sources`, not hardcoded
- **FR-015**: Every new source MUST be present in the central `SOURCES` registry dict with: `fetcher` class, `loader` callable, `requires_file` flag, and `default_days_back` (or `None` for non-incremental sources)
- **FR-016**: Every new fetcher MUST return a dict matching the canonical shape: `{status: 'success'|'failed', records: List[Dict], hash: str|None}` — loaders MUST return `{status, records_inserted, records_updated, errors: List[str]}`
- **FR-016a**: `BaseFetcher` MUST implement retry-with-exponential-backoff for HTTP API calls. Each source entry in `SOURCES` MAY specify `max_retries` (default: 3) and `retry_base_delay_seconds` (default: 2). A `429 Too Many Requests` or transient network error triggers a retry; a final exhausted retry logs the error and returns `status: 'failed'`

**SEC EDGAR**

- **FR-017**: The platform MUST fetch the most recent 10-K and 20-F annual filings from SEC EDGAR for a configured list of pharmaceutical companies, identified by CIK
- **FR-018**: EDGAR filing records MUST store: CIK, company name, ticker, filing type, fiscal year end date, filing date, accession number, and full document text in an inline `TEXT` column — PostgreSQL TOAST handles compression automatically; no separate overflow table or object storage is required
- **FR-019**: A silver-layer transformation MUST flag filings that contain drug-specific revenue disclosures (detected via keyword presence) to support downstream prioritization

**Agent System**

- **FR-024**: The platform MUST include 7 enrichment agents: 6 domain-specific CMS agents (service line inference, IDN hierarchy, referral network, contact verification, staffing decomposition, equipment inventory) plus a publication evidence extraction agent that reads publication abstracts from the silver layer and writes structured clinical endpoints to `mol_silver.publication_evidence`
- **FR-024a**: The publication evidence extraction agent MUST eliminate the dependency on the `xenon` schema — `mol_gold.trial_outcomes` MUST read from `mol_silver.publication_evidence` (not `xenon.publication_evidence`). The `xenon` schema is retained for the Xenon application's own use but removed from dk-data-FE's PostgREST exposure
- **FR-024b**: The PostgREST configuration MUST expose **silver and gold only** for all domain namespaces — following the established pattern where `mol_silver` and `mol_gold` are exposed but `mol_bronze` and `mol_raw` are not. This feature adds `hcs_silver` and `hcs_gold` to the `PGRST_DB_SCHEMAS` list in `k8s/apps/postgrest/base/configmap.yaml`. Bronze schemas (`mol_bronze`, `hcs_bronze`) and raw schemas (`mol_raw`, `hcs_raw`) MUST never be added to the exposure list
- **FR-025**: Every agent MUST route all LLM calls through the shared LiteLLM proxy — no direct API calls to any LLM provider
- **FR-026**: Records produced with confidence below 0.5 MUST be written to a quarantine table and excluded from live silver views until manually reviewed and resolved
- **FR-027**: Records produced with confidence between 0.5 and 0.79 MUST be written to the silver layer with a `needs_review` flag set to TRUE
- **FR-028**: Agents MUST be triggerable both on a monthly scheduled basis and on demand via API — a single agent run MUST NOT require a full pipeline restart

**Data Tools Gateway**

- **FR-029**: The platform MUST expose a tool registry listing all available data sources (CMS and molecule) with metadata: category, supported query keys, and last-refresh timestamp. The registry MUST be implemented by extending the existing `services/mcp/tool_registry.py` `TOOL_REGISTRY` dict — not by creating a parallel `services/data_tools/` directory
- **FR-030**: For any registered source, the platform MUST provide a backfill endpoint that fetches fresh upstream data and runs the silver/gold transformation without manual intervention. Freshness checking MUST extend `services/data_platform/data_freshness_monitor.py` — not duplicate it in a new module
- **FR-031**: Before triggering an external fetch, the gateway MUST check local data freshness and skip the external call if sufficiently recent data exists

**Clinical Evidence Silver Layer**

- **FR-032**: The platform MUST maintain a `mol_silver.publication_evidence` table storing LLM-extracted clinical endpoints (hazard ratio, p-value, response rate, median survival, sample size) deduplicated by content hash, with `confidence_score` and `needs_review` columns
- **FR-033**: `mol_gold.trial_outcomes` MUST UNION `mol_silver.clinical_trials` (registry-sourced, confidence = 1.0) with `mol_silver.publication_evidence` (LLM-extracted, confidence ≥ 0.40) — no reference to the `xenon` schema

**Data Integrity and Migration**

- **FR-020**: All schema changes MUST be delivered as a single consolidated migration script that can be reviewed, tested, and rolled back as a unit — no split migrations across the PR
- **FR-021**: The migration MUST reflect only the delta from the current main-branch schema — not a replay of 016 branch migrations, which reference dropped schemas and renamed columns that no longer apply
- **FR-022**: Any migration step that drops or renames columns or schemas MUST be preceded by a documented pre-flight check confirming: production backup taken, no active queries on affected schema, rollback script available
- **FR-023**: All existing tests MUST pass after the migration is applied — zero regressions in previously working data sources
- **FR-034**: A Grafana alert rule MUST be added that fires when any registered source accumulates ≥ 3 consecutive failed run entries in `meta.refresh_log` — the alert MUST identify the source name and timestamp of the first failure in the sequence

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

- **SC-001**: All 28 CMS PUF sources are registered in `meta.data_sources` and produce entries in `meta.refresh_log` after their first scheduled run — zero sources run silently without a log entry
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
- **SC-013**: When a source is manually forced to fail 3 consecutive times in a staging environment, the Grafana alert fires within one alert evaluation cycle and names the affected source

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
- PostgREST exposure of raw schemas (`mol_raw`, `hcs_raw`, or any `*_raw` namespace) — raw layer is internal pipeline state, never queryable via API
- Uplift/sync of monitoring config to dk-alchemy — tracked separately in dk-data-FE#145

## Implementation Order

Each piece can be independently tested and merged if needed:

1. **Consolidated migration** — audit all 57 016 migrations against current main schema; write the delta-only consolidated script; apply to staging; verify existing tests pass
2. **CMS PUF fetchers and loaders** (P1) — 28 sources using existing file-based hash-skip pattern; register all in `meta.data_sources` and `SOURCES` dict
3. **Regulatory and clinical sources** (P2) — EMA first, then Cochrane, EuropePMC, DrugBank, NIH Reporter, PubChem; each logged via `log_to_meta()`
4. **Market summary silver view** — after CMS and EMA are verified
5. **Agent system** (P4) — port 7 agent files (6 CMS domain agents + publication evidence extractor) + quarantine table + agents API router + CronJob + K8s Job template
6. **Data tools gateway** (P5) — extend `services/mcp/tool_registry.py` with 28 new CMS `ToolDefinition` entries; add adapters to `services/mcp/adapters/`; add `is_fresh()` to `services/data_platform/data_freshness_monitor.py`; add `api/routes/data_tools.py` router backed by existing `TOOL_REGISTRY`; no new `services/data_tools/` directory
7. **`mol_silver.publication_evidence`** — new silver table + SQLMesh INCREMENTAL model; restore `mol_gold.trial_outcomes` reading from silver; remove `xenon` from PostgREST schema list
8. **SQLMesh scheduler with advisory lock** — deadlock prevention deployment
9. **SEC EDGAR** (P6) — independent of other sources; can ship in this PR or a follow-on

---

## Technical Implementation Blueprint

This section defines the exact medallion architecture, table schemas, column names, SQLMesh model directives, and entity linking strategies required for implementation. All column names reflect actual upstream API field names.

---

### Canonical Ingestion Patterns

Every new source introduced in this feature **must** follow the patterns established on the main branch. This section documents those patterns as implementation constraints — not suggestions.

#### State tracking infrastructure (already exists on main)

The platform tracks fetch state through two tables and two utility functions. New sources register in these tables and call these functions — they do not invent alternative state mechanisms.

| Asset | Purpose |
|---|---|
| `meta.data_sources` | One row per registered source. Stores `source_name`, `last_successful_refresh`, `last_refresh_status`, `default_days_back` |
| `meta.refresh_log` | Append-only run log. One row per run. Stores `source_name`, `run_started_at`, `run_ended_at`, `records_fetched`, `records_inserted`, `records_updated`, `status`, `errors` |
| `log_to_meta(source_name, result)` | Writes one row to `meta.refresh_log` AND updates `meta.data_sources`. Called after every run, success or failure |
| `_compute_days_back(source, source_info)` | Reads `last_successful_refresh` from `meta.data_sources`, returns `elapsed_days + 1` as the lookback window. Returns `None` for non-incremental (bulk/file) sources — caller skips date windowing when `None` |
| `silver.publications` | Canonical publication consolidation (PubMed + OpenAlex + Cochrane + RSS + EuropePMC). Existing model — extend with CTEs, do not replace |

**`log_to_meta` contract** — the `result` dict passed to `log_to_meta` must contain exactly these keys:

```python
result = {
    "status": "success" | "failed" | "partial",
    "records_fetched": int,
    "records_inserted": int,
    "records_updated": int,
    "errors": List[str],   # empty list on success
}
```

**`_compute_days_back` contract** — always pass the source name and its `meta.data_sources` row:

```python
days_back = _compute_days_back(source_name, source_info)
# days_back is None  → non-incremental source; do not apply a date filter
# days_back is int   → use as lookback window for API date parameter
```

If `last_successful_refresh` is NULL (first run), the function returns `default_days_back` from the source registration.

#### SOURCES registry (central dispatch)

Every source must have an entry in the top-level `SOURCES` dict in the ingestion module. Required keys differ by source type:

- **File-based sources** (`requires_file: True`): `name`, `description`, `loader`, `requires_file`, `default_days_back`. Do **not** include a `fetcher` key — file acquisition is handled externally (CronJob downloads to a mounted volume).
- **API sources** (`requires_file: False`): all of the above **plus** `fetcher` (the fetcher class). May optionally include `max_retries` and `retry_base_delay_seconds`.

```python
SOURCES = {
    # File-based source — NO fetcher key
    "cms_part_d_spending": {
        "loader": load_cms_part_d_spending,   # Callable
        "requires_file": True,                # True = file acquisition is external
        "default_days_back": None,            # None = non-incremental (full file replacement)
    },
    # API source — fetcher key required
    "europepmc": {
        "fetcher": EuropePMCFetcher,          # Class, not instance (API sources only)
        "loader": load_europepmc,
        "requires_file": False,
        "default_days_back": 30,              # int = incremental API source
        "max_retries": 3,                     # optional; default 3
        "retry_base_delay_seconds": 2,        # optional; default 2 (exponential backoff)
    },
    # ... all other sources follow same shape per their type
}
```

#### BaseFetcher contract

Every fetcher class must extend `BaseFetcher`. The constructor signature is fixed:

```python
class MySourceFetcher(BaseFetcher):
    def __init__(self, data_dir=None):
        super().__init__(data_dir=data_dir)
        # No `params` kwarg. No manifest system. No other constructor args.
```

Every fetcher's `fetch()` method must return a dict with exactly these keys:

```python
return {
    "status": "success" | "failed",
    "records": List[Dict],   # raw records as dicts; empty list on failure
    "hash": str | None,      # MD5 of source file for file-based; None for API sources
}
```

#### File-based hash-skip (file-based sources only)

For sources where `requires_file: True`, the loader must check whether the file content has already been ingested before inserting any records:

```python
# 1. Compute MD5 of the downloaded file
file_hash = md5(file_bytes)

# 2. Check raw table for existing records with this hash
existing = conn.execute(
    "SELECT COUNT(*) FROM hcs_raw.{table} WHERE _source_hash = %s",
    [file_hash]
).scalar()

# 3. Skip insert if file has not changed; log the skip via log_to_meta
if existing > 0:
    return {"status": "success", "records_inserted": 0, "records_updated": 0,
            "records_fetched": existing, "errors": []}
```

This logic is already implemented for existing CMS sources on main. New CMS PUF fetchers must replicate this pattern — they must not introduce a different deduplication mechanism.

#### Raw table pattern selection rule

| Source type | Pattern | Raw table characteristics |
|---|---|---|
| HTTP API (EuropePMC, EMA, NIH Reporter, PubChem) | Pattern A: JSONB archive | `response_body JSONB`, `processed_to_bronze BOOLEAN DEFAULT FALSE` |
| File download (all 28 CMS PUF sources) | Pattern B: Direct-normalized | Typed columns matching file schema, `_source_hash VARCHAR(64)`, `_loaded_at TIMESTAMP` |

Never mix patterns. A CMS source must never use JSONB. An API source must never use `_source_hash` file-skip logic (API responses are deduplicated by record ID in bronze instead).

---

### Schema Namespace Layout

| Schema | Domain | Layer |
|---|---|---|
| `mol_raw` | Molecule / regulatory / clinical | Raw (JSONB archive) |
| `hcs_raw` | Healthcare / CMS PUF | Raw (direct-normalized typed columns) |
| `mol_bronze` | Molecule domain | Bronze (typed extraction from JSONB) |
| `hcs_bronze` | Healthcare / CMS domain | Bronze (typed extraction) |
| `mol_silver` | Molecule domain | Silver (normalized, entity-linked) |
| `hcs_silver` | Healthcare / CMS domain | Silver (normalized) |
| `mol_gold` | Molecule domain | Gold (aggregated, decision-ready) |
| `hcs_gold` | Healthcare / CMS domain | Gold (aggregated) |

> **config.yaml prerequisite**: Before any HCS SQLMesh model can run, `src/dk_data/sqlmesh/config.yaml` must have `hcs_raw`, `hcs_bronze`, `hcs_silver`, and `hcs_gold` added to its `physical_schema_mapping` section. See T060.

---

### Raw Layer

**Two distinct raw table patterns** — determined by source type:

#### Pattern A: JSONB archive (API-based sources: EuropePMC, EMA, NIH Reporter)

Used when the platform fetches from an HTTP API and must preserve the full response for bronze re-processing.

```sql
CREATE TABLE mol_raw.{source} (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL,
    api_version         VARCHAR(20) DEFAULT 'v1',
    response_status     INTEGER NOT NULL,
    response_body       JSONB NOT NULL,           -- unmodified API response
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    _source_hash        VARCHAR(64)
);
CREATE INDEX ON mol_raw.{source} (processed_to_bronze, request_timestamp);
CREATE INDEX ON mol_raw.{source} (response_body_hash);
```

#### Pattern B: Direct-normalized (file-based CMS PUF sources)

Used for CMS sources where files are downloaded locally and parsed into typed columns. No JSONB — each row is one parsed record from the CSV/Excel file.

```sql
CREATE TABLE hcs_raw.{source} (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- source-specific typed columns (see per-source definitions below)
    _source_hash VARCHAR(64),                     -- MD5 of source file
    _loaded_at   TIMESTAMP NOT NULL DEFAULT NOW()
);
```

File-based skip-if-loaded check (existing pattern, must be reused):
```python
COUNT(*) FROM hcs_raw.{table} WHERE _source_hash = %s  →  skip if > 0
```

#### Key CMS PUF Raw Table Schemas

**`hcs_raw.cms_part_d_spending`** — CMS Part D drug spending (API: data.cms.gov, dataset `7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b`):
```sql
brand_name              VARCHAR(200),
generic_name            VARCHAR(200),
total_spending          NUMERIC(15,2),   -- field: Tot_Spndng / total_spending
total_claims            INTEGER,         -- field: Tot_Clms / total_claims
total_beneficiaries     INTEGER,         -- field: Tot_Benes / total_beneficiaries
avg_cost_per_claim      NUMERIC(10,2),   -- field: Avg_Spnd_Per_Clm / avg_cost_per_claim
year                    INTEGER          -- field: Year / year (default 2023)
```

Note: CMS API uses inconsistent field naming across dataset versions (`Brnd_Name` vs `brand_name`). Fetcher uses first-not-null dual-key lookup for all fields.

**`hcs_raw.cms_part_b_spending`** — CMS Part B drug spending:
```sql
hcpcs_code              VARCHAR(10),
hcpcs_description       VARCHAR(500),
brand_name              VARCHAR(200),
generic_name            VARCHAR(200),
total_spending          NUMERIC(15,2),
total_claims            INTEGER,
total_beneficiaries     INTEGER,
avg_cost_per_claim      NUMERIC(10,2),
avg_cost_per_day        NUMERIC(10,2),
year                    INTEGER
```

**`hcs_raw.cms_open_payments`** — Physician Open Payments:
```sql
record_id               VARCHAR(100),
physician_npi           VARCHAR(20),
physician_first_name    VARCHAR(100),
physician_last_name     VARCHAR(100),
physician_specialty     VARCHAR(200),
physician_state         VARCHAR(2),
manufacturer_name       VARCHAR(200),
product_name            VARCHAR(200),
payment_amount          NUMERIC(12,2),
payment_nature          VARCHAR(100),
payment_form            VARCHAR(100),
payment_date            DATE,
payment_year            INTEGER
```

**`hcs_raw.cms_nppes`** — National Provider Identifier registry (~8 GB, NPPES weekly bulk file):
```sql
npi                     VARCHAR(20) NOT NULL,
entity_type_code        VARCHAR(1),          -- 1=individual, 2=organization
provider_last_name      VARCHAR(100),
provider_first_name     VARCHAR(100),
provider_organization_name VARCHAR(200),
provider_credential     VARCHAR(100),
provider_taxonomy_code_1 VARCHAR(20),
provider_license_number_1 VARCHAR(50),
provider_license_state_1  VARCHAR(2),
provider_address_state   VARCHAR(2),
provider_address_zip     VARCHAR(10),
enumeration_date         DATE,
last_update_date         DATE
```

**`hcs_raw.cms_inpatient_puf`** — Medicare inpatient hospital DRG data:
```sql
ccn                       VARCHAR(20) NOT NULL,   -- CMS Certification Number
drg_code                  VARCHAR(10) NOT NULL,
drg_description           VARCHAR(300),
total_discharges          INTEGER,
avg_covered_charges       NUMERIC(12,2),
avg_total_payments        NUMERIC(12,2),
avg_medicare_payments     NUMERIC(12,2)
```

**`hcs_raw.cms_physician_puf`** — Physician and Other Supplier PUF:
```sql
npi                       VARCHAR(20) NOT NULL,
provider_last_name        VARCHAR(100),
provider_first_name       VARCHAR(100),
provider_credentials      VARCHAR(100),
provider_gender           VARCHAR(1),
provider_entity_type      VARCHAR(1),
provider_zip5             VARCHAR(5),
provider_state            VARCHAR(2),
hcpcs_code               VARCHAR(10) NOT NULL,
hcpcs_description        VARCHAR(500),
place_of_service         VARCHAR(1),
hcpcs_drug_indicator     VARCHAR(1),
total_services           NUMERIC(12,2),
total_medicare_allowed   NUMERIC(12,2),
total_medicare_payment   NUMERIC(12,2),
total_benes              INTEGER,
year                     INTEGER
```

**`hcs_raw.cms_hospital_general_info`** — Hospital Compare general info:
```sql
facility_id              VARCHAR(20) NOT NULL,    -- CMS Certification Number
facility_name            VARCHAR(200),
address                  VARCHAR(300),
city                     VARCHAR(100),
state                    VARCHAR(2),
zip_code                 VARCHAR(10),
county_name              VARCHAR(100),
phone_number             VARCHAR(20),
hospital_type            VARCHAR(100),
hospital_ownership       VARCHAR(100),
emergency_services       BOOLEAN
```

---

### Bronze Layer

Bronze reads from raw tables and extracts typed columns. Two patterns mirror the raw patterns.

#### JSONB extraction (mol_bronze, API sources)

```sql
MODEL (
    name mol_bronze.europepmc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    audits (not_null(columns := (pmid)), unique_values(columns := (pmid))),
    grain pmid
);

SELECT
    r.id                                            AS raw_id,
    r.request_timestamp,
    r.response_body->>'id'                          AS europepmc_id,
    r.response_body->>'pmid'                        AS pmid,
    r.response_body->>'doi'                         AS doi,
    r.response_body->>'title'                       AS title,
    r.response_body->>'abstractText'                AS abstract,
    r.response_body->>'source'                      AS source,       -- MED, PMC, PPR
    (r.response_body->>'pubYear')::INTEGER          AS pub_year,
    r.response_body->'journalInfo'->>'journal'      AS journal_name, -- nested object
    r.response_body->'journalInfo'->>'issn'         AS journal_issn,
    r.response_body->'journalInfo'->>'volume'       AS volume,
    r.response_body->'authorList'->'author'         AS authors_jsonb, -- JSONB array kept intact
    r.response_body->>'isOpenAccess'                AS is_open_access_raw,
    r.response_body->'meshHeadingList'->'meshHeading' AS mesh_terms_jsonb,
    (r.response_body->>'citedByCount')::INTEGER     AS cited_by_count,
    r.response_body                                 AS raw_json,
    NOW()                                           AS ingested_at
FROM mol_raw.europepmc r
WHERE r.processed_to_bronze = FALSE
  AND r.response_status = 200
  AND r.request_timestamp BETWEEN @start_dt AND @end_dt;
```

```sql
MODEL (
    name mol_bronze.ema_regulatory,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 200
    ),
    cron '@weekly',
    audits (not_null(columns := (product_number))),
    grain product_number
);

-- EMA JSON field names (from medicines JSON report):
SELECT
    r.response_body->>'Product number'             AS product_number,
    r.response_body->>'Medicine name'              AS medicine_name,
    r.response_body->>'Active substance'           AS active_substance,
    r.response_body->>'INN'                        AS inn,
    r.response_body->>'Authorisation status'       AS authorisation_status,
    r.response_body->>'Product type'               AS product_type,
    r.response_body->>'Therapeutic area'           AS therapeutic_area,
    r.response_body->>'ATC code'                   AS atc_code,
    r.response_body->>'Marketing authorisation date' AS marketing_authorisation_date,
    r.response_body->>'Revision date'              AS revision_date,
    r.response_body->>'URL'                        AS epar_url,
    r.response_body->>'Condition/indication'       AS condition_indication,
    r.response_body                                AS raw_json
FROM mol_raw.ema_regulatory r
WHERE r.processed_to_bronze = FALSE
  AND r.response_status = 200
  AND r.request_timestamp BETWEEN @start_dt AND @end_dt;
```

#### CMS bronze (typed pass-through from direct-normalized raw)

CMS raw tables already have typed columns. Bronze casts and validates:

```sql
MODEL (
    name hcs_bronze.cms_part_d_spending,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@monthly',
    audits (not_null(columns := (generic_name, year))),
    grain (generic_name, year)
);

SELECT
    id                  AS raw_id,
    brand_name,
    UPPER(TRIM(generic_name))   AS generic_name,   -- normalize case
    total_spending::NUMERIC(15,2),
    total_claims::INTEGER,
    total_beneficiaries::INTEGER,
    avg_cost_per_claim::NUMERIC(10,2),
    COALESCE(year, 2023)        AS year,
    _source_hash,
    _loaded_at                  AS ingested_at
FROM hcs_raw.cms_part_d_spending
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
```

```sql
MODEL (
    name hcs_bronze.cms_inpatient_puf,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn, drg_code))),
    grain (ccn, drg_code)
);

SELECT
    ccn,
    drg_code,
    drg_description,
    total_discharges::INTEGER,
    avg_covered_charges::NUMERIC(12,2),
    avg_total_payments::NUMERIC(12,2),
    avg_medicare_payments::NUMERIC(12,2),
    _source_hash,
    _loaded_at AS ingested_at
FROM hcs_raw.cms_inpatient_puf
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
```

---

### Silver Layer

Silver normalizes bronze records and links them to the canonical molecule entity (`mol_silver.molecules.molecule_id`). Entity linking is the core function of this layer.

#### Entity linking strategies (by source)

| Source | Primary link | Fallback | Guard |
|---|---|---|---|
| EMA Regulatory | `LOWER(active_substance) = LOWER(m.canonical_name)` | `LOWER(inn) = LOWER(m.canonical_name)` | — |
| Cochrane Reviews | `LOWER(title) LIKE '%' \|\| LOWER(m.canonical_name) \|\| '%'` | — | `LENGTH(canonical_name) > 4` |
| DrugBank | `LOWER(inchi_key) = LOWER(m.inchi_key)` (small molecules) | `LOWER(name) = LOWER(m.canonical_name)` (biologics, when inchi_key IS NULL) | — |
| Drug Spending (Part D) | `LOWER(generic_name) = LOWER(m.canonical_name)` | `LOWER(brand_name) = LOWER(m.canonical_name)` | — |
| Drug Spending (Part B) | `LOWER(hcpcs_description) ≈ LOWER(m.canonical_name)` | — | hcpcs_description substring |
| Physician Payments | `LOWER(product_name) = LOWER(m.canonical_name)` | — | — |
| Research Grants (NIH) | `LOWER(project_title) LIKE '%' \|\| LOWER(m.canonical_name) \|\| '%'` | — | `LENGTH(canonical_name) > 4` |
| PubChem | `LOWER(inchi_key) = LOWER(m.inchi_key)` | — | — |
| EuropePMC | `LOWER(title) LIKE '%' \|\| LOWER(m.canonical_name) \|\| '%'` | — | `LENGTH(canonical_name) > 4` — Consolidated into `silver.publications` (5th CTE) — linking happens within `silver.publications` via `LOWER(title) LIKE` |
| Publication Evidence | `pmid = p.pmid` (join to `silver.publications`) | — | — |

#### `mol_silver.ema_regulatory`

```sql
MODEL (
    name mol_silver.ema_regulatory,
    kind FULL,
    cron '@weekly',
    audits (not_null(columns := (product_number, active_substance)))
);

SELECT
    gen_random_uuid()                               AS ema_regulatory_id,
    COALESCE(m_sub.molecule_id, m_inn.molecule_id) AS molecule_id,
    b.product_number,
    b.medicine_name                                 AS product_name,
    b.active_substance,
    b.inn,
    b.atc_code,
    b.authorisation_status                          AS authorization_status,
    b.marketing_authorisation_date::DATE            AS authorization_date,
    b.revision_date::DATE,
    b.product_type                                  AS medicine_type,
    b.therapeutic_area,
    b.condition_indication,
    b.epar_url,
    NOW()                                           AS _loaded_at
FROM mol_bronze.ema_regulatory b
LEFT JOIN mol_silver.molecules m_sub
       ON LOWER(m_sub.canonical_name) = LOWER(b.active_substance)
LEFT JOIN mol_silver.molecules m_inn
       ON m_sub.molecule_id IS NULL
      AND b.inn IS NOT NULL
      AND LOWER(m_inn.canonical_name) = LOWER(b.inn);
```

#### `mol_silver.drug_spending`

```sql
MODEL (
    name mol_silver.drug_spending,
    kind FULL,
    cron '@monthly',
    audits (not_null(columns := (generic_name, program, year)))
);

-- Part D spending
WITH part_d AS (
    SELECT
        COALESCE(m_gen.molecule_id, m_brand.molecule_id)   AS molecule_id,
        b.brand_name,
        b.generic_name,
        'Part D'                                            AS program,
        b.year,
        b.total_claims,
        b.total_beneficiaries,
        b.total_spending,
        b.avg_cost_per_claim,
        NULL::NUMERIC                                       AS avg_cost_per_day,
        NULL::NUMERIC                                       AS avg_cost_per_beneficiary,
        NULL::INTEGER                                       AS total_supply_days
    FROM hcs_bronze.cms_part_d_spending b
    LEFT JOIN mol_silver.molecules m_gen
           ON LOWER(m_gen.canonical_name) = LOWER(b.generic_name)
    LEFT JOIN mol_silver.molecules m_brand
           ON m_gen.molecule_id IS NULL
          AND LOWER(m_brand.canonical_name) = LOWER(b.brand_name)
),
-- Part B spending
part_b AS (
    SELECT
        m_gen.molecule_id,
        b.brand_name,
        b.generic_name,
        'Part B'                                            AS program,
        b.year,
        b.total_claims,
        b.total_beneficiaries,
        b.total_spending,
        b.avg_cost_per_claim,
        b.avg_cost_per_day,
        (b.total_spending / NULLIF(b.total_beneficiaries,0)) AS avg_cost_per_beneficiary,
        NULL::INTEGER                                       AS total_supply_days
    FROM hcs_bronze.cms_part_b_spending b
    LEFT JOIN mol_silver.molecules m_gen
           ON LOWER(m_gen.canonical_name) = LOWER(b.generic_name)
)
SELECT gen_random_uuid() AS spending_id, * FROM part_d
UNION ALL
SELECT gen_random_uuid() AS spending_id, * FROM part_b;
```

#### `mol_silver.publication_evidence` (new — ported from xenon agent)

```sql
MODEL (
    name mol_silver.publication_evidence,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key content_hash
    ),
    cron '@weekly',
    audits (
        not_null(columns := (content_hash, endpoint_name, confidence_score)),
        unique_values(columns := (content_hash))
    ),
    grain content_hash
);
```

Table schema (written by publication evidence extraction agent, not by a SELECT transformation):
```sql
CREATE TABLE mol_silver.publication_evidence (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id           UUID,                         -- FK mol_silver.molecules
    trial_nct_id          VARCHAR(20),
    endpoint_name         VARCHAR(200) NOT NULL,
    endpoint_type         VARCHAR(50)
        CHECK (endpoint_type IN ('primary','secondary','exploratory')),
    hazard_ratio          NUMERIC(8,4),
    p_value               NUMERIC(10,8),
    response_rate         NUMERIC(5,2),
    median_survival_months NUMERIC(6,1),
    sample_size           INTEGER,
    confidence_score      NUMERIC(3,2) NOT NULL
        CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    doi                   VARCHAR(100),
    pmid                  VARCHAR(20),
    extraction_metadata   JSONB,
    content_hash          VARCHAR(64) NOT NULL UNIQUE,  -- SHA256(pmid + endpoint_name)
    needs_review          BOOLEAN NOT NULL DEFAULT FALSE,
    _loaded_at            TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ON mol_silver.publication_evidence (molecule_id);
CREATE INDEX ON mol_silver.publication_evidence (confidence_score)
    WHERE confidence_score >= 0.40;
CREATE INDEX ON mol_silver.publication_evidence (trial_nct_id)
    WHERE trial_nct_id IS NOT NULL;
```

#### `hcs_silver.cms_drug_market`

```sql
MODEL (
    name hcs_silver.cms_drug_market,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ndc)),
        unique_values(columns := (ndc))
    ),
    grain ndc
);

-- Key CTEs:
-- 1. ndc_per_drug: COUNT NDCs per generic_name (for Part D spending proration)
-- 2. spending_d: SUM Part D spending by generic_name, prorated by ndc_count
-- 3. spending_b: SUM Part B spending by hcpcs_code
-- 4. usp_lookup: DISTINCT ON (ndc) from cms_usp, ordered by (usp_category, usp_class)
-- 5. rbcs_lookup: direct join on hcpcs_code

-- Key columns:
SELECT
    n.ndc,
    n.brand_name,
    n.generic_name,
    n.labeler_name,
    n.route,
    n.dosage_form,
    n.product_type,
    -- Spending (Part D prorated: total / ndc_count to avoid fan-out)
    ROUND(sd.total_part_d_spending / NULLIF(nd.ndc_count, 0), 2) AS total_part_d_spending,
    sd.total_part_d_claims,
    sb.total_part_b_spending,
    sb.total_part_b_claims,
    -- Formulary
    f.formulary_coverage_pct,
    f.avg_tier_level,                           -- NULL if no data, not 0
    -- Classifications
    r.rbcs_category,
    r.rbcs_subcategory,
    u.usp_category,
    u.usp_class,
    NOW() AS profile_built_at
FROM hcs_bronze.cms_ndc n
LEFT JOIN ndc_per_drug nd USING (generic_name)
LEFT JOIN spending_d sd USING (generic_name)
LEFT JOIN spending_b sb ON ...
LEFT JOIN formulary_coverage f USING (ndc)
LEFT JOIN rbcs_lookup r USING (hcpcs_code)
LEFT JOIN usp_lookup u USING (ndc);
```

---

### Gold Layer

Gold produces aggregated, decision-ready views. No raw data is written here directly — all inputs come from silver.

#### `mol_gold.trial_outcomes` (restored from `.removed`)

```sql
MODEL (
    name mol_gold.trial_outcomes,
    kind FULL,
    cron '@weekly',
    grain (molecule_id, trial_nct_id, endpoint_name, evidence_source)
);

WITH registry_outcomes AS (
    -- Structured data from ClinicalTrials.gov (confidence = 1.0)
    SELECT
        ct.molecule_id,
        ct.nct_id                           AS trial_nct_id,
        'clinicaltrials_gov'                AS evidence_source,
        (o->>'measure')                     AS endpoint_name,
        NULL::NUMERIC                       AS hazard_ratio,
        NULL::NUMERIC                       AS p_value,
        NULL::NUMERIC                       AS response_rate,
        NULL::NUMERIC                       AS median_survival_months,
        ct.enrollment                       AS sample_size,
        1.0::NUMERIC                        AS confidence_score,
        ct.start_date::DATE                 AS evidence_date
    FROM mol_silver.clinical_trials ct,
         jsonb_array_elements(ct.primary_outcomes) AS o
    WHERE ct.molecule_id IS NOT NULL
),
publication_outcomes AS (
    -- LLM-extracted endpoints from publications (confidence >= 0.40, not needs_review)
    SELECT
        pe.molecule_id,
        pe.trial_nct_id,
        'publication'                       AS evidence_source,
        pe.endpoint_name,
        pe.hazard_ratio,
        pe.p_value,
        pe.response_rate,
        pe.median_survival_months,
        pe.sample_size,
        pe.confidence_score,
        pe._loaded_at::DATE                 AS evidence_date
    FROM mol_silver.publication_evidence pe
    WHERE pe.confidence_score >= 0.40
      AND pe.needs_review = FALSE
      AND pe.molecule_id IS NOT NULL
)
SELECT gen_random_uuid() AS id, *, NOW() AS created_at
FROM registry_outcomes
UNION ALL
SELECT gen_random_uuid() AS id, *, NOW() AS created_at
FROM publication_outcomes;
```

#### `mol_gold.market_summary`

```sql
MODEL (
    name mol_gold.market_summary,
    kind FULL,
    cron '@monthly',
    audits (not_null(columns := (molecule_id)), unique_values(columns := (molecule_id))),
    grain molecule_id
);

SELECT
    m.molecule_id,
    m.canonical_name,
    m.development_status,
    m.max_phase,
    -- Pricing (CMS)
    SUM(ds.total_part_d_spending)                       AS total_part_d_spending,
    SUM(ds.total_part_b_spending)                       AS total_part_b_spending,
    SUM(ds.total_part_d_claims + ds.total_part_b_claims) AS total_claims,
    -- Physician payments
    SUM(pp.payment_amount)                              AS total_physician_payments,
    COUNT(DISTINCT pp.physician_npi)                    AS paying_physician_count,
    -- Regulatory status
    MAX(er.authorization_date)                          AS latest_ema_authorization,
    MAX(er.authorization_status)                        AS ema_status,
    -- Clinical evidence volume
    COUNT(DISTINCT cr.review_id)                        AS cochrane_review_count,
    COUNT(DISTINCT to_.trial_nct_id)                    AS trial_count,
    COUNT(DISTINCT CASE WHEN to_.evidence_source = 'publication' THEN to_.trial_nct_id END)
                                                        AS publication_evidence_trial_count,
    -- Research funding
    SUM(rg.award_amount)                                AS total_nih_funding,
    COUNT(DISTINCT rg.project_number)                   AS nih_grant_count,
    -- Compound identity
    pc.cid                                              AS pubchem_cid,
    pc.molecular_weight,
    pc.xlogp,
    pc.tpsa,
    NOW()                                               AS summary_built_at
FROM mol_silver.molecules m
LEFT JOIN mol_silver.drug_spending ds USING (molecule_id)
LEFT JOIN mol_silver.physician_payments pp USING (molecule_id)
LEFT JOIN mol_silver.ema_regulatory er USING (molecule_id)
LEFT JOIN mol_silver.cochrane_reviews cr USING (molecule_id)
LEFT JOIN mol_gold.trial_outcomes to_ USING (molecule_id)
LEFT JOIN mol_silver.research_grants rg USING (molecule_id)
LEFT JOIN mol_silver.pubchem pc USING (molecule_id)
WHERE m.needs_review = FALSE
GROUP BY m.molecule_id, m.canonical_name, m.development_status, m.max_phase,
         pc.cid, pc.molecular_weight, pc.xlogp, pc.tpsa;
```

#### `hcs_gold.cms_drug_market_profile`

```sql
MODEL (
    name hcs_gold.cms_drug_market_profile,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ndc)),
        unique_values(columns := (ndc))
    ),
    grain ndc
);

SELECT
    s.*,
    -- Market share: this NDC's spend as % of all spending
    ROUND(
        (s.total_part_d_spending + s.total_part_b_spending)
        / NULLIF(SUM(s.total_part_d_spending + s.total_part_b_spending) OVER (), 0) * 100,
        4
    )                                                               AS market_share_pct,
    -- Cost per claim (combined)
    ROUND(
        (s.total_part_d_spending + s.total_part_b_spending)
        / NULLIF(s.total_part_d_claims + s.total_part_b_claims, 0),
        2
    )                                                               AS combined_cost_per_claim,
    -- Category rank by spend (NULLS LAST = unclassified drugs rank last)
    RANK() OVER (
        PARTITION BY s.rbcs_category
        ORDER BY (s.total_part_d_spending + s.total_part_b_spending) DESC NULLS LAST
    )                                                               AS category_spend_rank,
    -- Category rank by formulary coverage
    RANK() OVER (
        PARTITION BY s.rbcs_category
        ORDER BY s.formulary_coverage_pct DESC NULLS LAST
    )                                                               AS category_formulary_rank
FROM hcs_silver.cms_drug_market s;
```

---

### SQLMesh Model Reference

| Model | Kind | Grain | Cron |
|---|---|---|---|
| `mol_bronze.europepmc` | INCREMENTAL_BY_TIME_RANGE | pmid | @weekly |
| `mol_bronze.ema_regulatory` | INCREMENTAL_BY_TIME_RANGE | product_number | @weekly |
| `mol_bronze.nih_reporter` | INCREMENTAL_BY_TIME_RANGE | project_number | @weekly |
| `hcs_bronze.cms_part_d_spending` | INCREMENTAL_BY_TIME_RANGE | (generic_name, year) | @monthly |
| `hcs_bronze.cms_part_b_spending` | INCREMENTAL_BY_TIME_RANGE | (hcpcs_code, year) | @monthly |
| `hcs_bronze.cms_inpatient_puf` | INCREMENTAL_BY_TIME_RANGE | (ccn, drg_code) | @monthly |
| `hcs_bronze.cms_open_payments` | INCREMENTAL_BY_TIME_RANGE | record_id | @monthly |
| `hcs_bronze.cms_nppes` | INCREMENTAL_BY_TIME_RANGE | npi | @weekly |
| `mol_silver.ema_regulatory` | FULL | product_number | @weekly |
| `mol_silver.cochrane_reviews` | FULL | review_id | @monthly |
| `mol_silver.drugbank` | FULL | drugbank_id | @monthly |
| `mol_silver.drug_spending` | FULL | (generic_name, program, year) | @monthly |
| `mol_silver.physician_payments` | FULL | source_record_id | @monthly |
| `mol_silver.research_grants` | FULL | project_number | @weekly |
| `mol_silver.pubchem` | FULL | cid | @weekly |
| `silver.publications` (extended) | INCREMENTAL_BY_UNIQUE_KEY (doi) | doi | @weekly |
| `mol_silver.publication_evidence` | INCREMENTAL_BY_UNIQUE_KEY (content_hash) | content_hash | @weekly |
| `hcs_silver.cms_drug_market` | FULL | ndc | @monthly |
| `mol_gold.trial_outcomes` | FULL | (molecule_id, trial_nct_id, endpoint_name, evidence_source) | @weekly |
| `mol_gold.market_summary` | FULL | molecule_id | @monthly |
| `hcs_gold.cms_drug_market_profile` | FULL | ndc | @monthly |

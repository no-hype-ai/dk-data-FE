# Research: Data Source Integration

**Feature**: 011-datasource-integration
**Date**: 2026-02-14

## R1: Molecule Ingestion Architecture

**Decision**: Tier 2A/3 sources join existing grouped CronJobs; no new fetcher code needed.

**Rationale**: The `RawIngestionService` base class in `raw_ingestion.py` already has complete subclasses for all 13 Tier 2A/3 sources. The `fetch_molecules.py` CLI accepts comma-separated source names via `--source`. The `REFRESH_SCHEDULE` dict already defines refresh intervals. The `should_refresh()` method checks if a source needs fetching based on its schedule tier, so weekly CronJobs can safely include monthly sources (they'll be skipped until their refresh interval elapses).

**Alternatives considered**:
- Individual CronJobs per molecule source: Rejected — 13 new manifests for sources that already work in the grouped pattern. Increases manifest sprawl without benefit.
- New tier-specific grouped jobs: Rejected — adds unnecessary complexity when the existing `should_refresh()` mechanism already handles tiered scheduling.

**Implementation detail**:
- Existing `mol-fetch-weekly` (`0 3 * * 0`): Add `ema,orange_book` to source list (weekly refresh)
- New `mol-fetch-monthly` (`0 8 1 * *`): Create for monthly sources — `bindingdb,sider,tdc_admet,kegg_drug,ttd,pharmgkb,imgt,cdc_vaccines,uniprot,rxnorm,dailymed,fda_drugs`
- No changes to `mol-fetch-daily` — it already handles `clinicaltrials,openfda`

## R2: CI Source Fetch Strategy (Hybrid)

**Decision**: High-priority CI sources (PubMed, OpenAlex) use broad daily ingest; lower-priority CI sources use query-scoped fetches with configurable search terms stored in the database.

**Rationale**: PubMed and OpenAlex are foundational publication databases where broad coverage is essential for competitive intelligence. Other CI sources (HTA bodies, patents, news) benefit from scoped queries that reduce volume and improve relevance. A `meta.ci_search_terms` table stores configurable drug/therapeutic-area terms.

**Alternatives considered**:
- Broad ingest for all: Rejected — some sources (SEC EDGAR, HTA) have massive datasets where unscoped fetching wastes storage and compute.
- Query-scoped for all: Rejected — PubMed and OpenAlex benefit from comprehensive coverage since downstream analytics aggregate across therapeutic areas.
- Fixed hardcoded terms: Rejected — search terms must evolve as the drug portfolio changes.

## R3: API View Scope

**Decision**: PostgREST API views created only for Tier 4 CI sources. Molecule sources defer to SQLMesh gold-level views.

**Rationale**: Molecule sources feed into the medallion pipeline (raw → bronze → silver → gold). Exposing raw-level views would provide unprocessed data that isn't useful for consumers. The SQLMesh feature (separate) will create `mol_api.*` views from gold tables. CI sources don't have a transform pipeline, so their raw tables are the final queryable layer.

**Alternatives considered**:
- Raw views for all: Rejected — exposes unprocessed molecule data and creates rework when gold views arrive.
- Staged (raw now, gold later): Rejected — consumers would build on raw views, then break when replaced by gold views.

## R4: CI Source Database Schema Pattern

**Decision**: CI sources use the `raw.*` schema (not `mol_raw.*`) with the standard audit columns pattern from the TAVR fetchers.

**Rationale**: CI sources (publications, patents, regulatory decisions, news) are not molecule-centric data. They don't feed into the medallion pipeline. They use the `BaseFetcher` pattern, not `RawIngestionService`. Placing them in `raw.*` maintains separation of concerns — `mol_raw.*` is for molecule pipeline data, `raw.*` is for standalone ingested data.

**Raw table pattern** (per CI source):
```sql
CREATE TABLE IF NOT EXISTS raw.[source_name] (
    [natural_key] VARCHAR(...) NOT NULL,
    [data_fields...],
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE ([natural_key])
);
```

**API view pattern** (per CI source):
```sql
CREATE OR REPLACE VIEW api.[view_name] AS
SELECT [fields] FROM raw.[source_name];
GRANT SELECT ON api.[view_name] TO web_anon;
GRANT SELECT ON api.[view_name] TO analyst;
```

## R5: Query-Scoped CI Search Terms Storage

**Decision**: Store configurable search terms in `meta.ci_search_terms` table for query-scoped CI sources.

**Rationale**: Query-scoped CI fetchers need a dynamic set of drug names, therapeutic areas, and MeSH terms to construct API queries. Storing these in the database (rather than config files or environment variables) allows the Admin App to manage them in the future and keeps configuration alongside the data.

**Schema**:
```sql
CREATE TABLE IF NOT EXISTS meta.ci_search_terms (
    term_id SERIAL PRIMARY KEY,
    term_type VARCHAR(50) NOT NULL,  -- 'drug_name', 'therapeutic_area', 'mesh_term', 'company'
    term_value VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (term_type, term_value)
);
```

## R6: Existing Molecule CronJob Schedule Conflicts

**Decision**: `mol-fetch-monthly` scheduled at `0 8 1 * *` (1st of month, 8 AM UTC).

**Rationale**: Available slot at hour 8. Existing schedule:
- 02: mol-fetch-daily, fetch-cms-all
- 03: mol-fetch-weekly
- 04: fetch-acc-tvc
- 05: fetch-hrsa
- 06: catalog-refresh, mol-transform (different purposes, can overlap)
- 07: sqlmesh-run
- 08: **AVAILABLE** → mol-fetch-monthly
- 10: mol-transform

Monthly job runs on 1st of month to avoid conflict with daily jobs that also run at hour 8.

## R7: ACC TVC Source Fix

**Decision**: Research required — likely needs manual CSV upload fallback.

**Rationale**: The ACC website no longer provides CSV downloads or a scrapeable interface for TVC certification data. The `ACCTVCFetcher` currently fails on every run. Options:
1. Check if ACC has a new API (research during implementation)
2. Implement manual CSV upload path via `load_acc_tvc_file()`
3. Disable the source if no data access method exists

This is P7 (lowest priority) and may not yield results. Implementation should focus on the manual upload fallback as the reliable path.

# Feature: TAVR Catalog Candidate Manifest Provisioning

## Summary

Provision `hcs_gold.tavr_catalog_candidate_manifest` — the Phase 0 dataset-discovery layer of the TAVR Benchmark Lab pipeline. The table catalogs candidate public datasets from Data.gov, CMS Data, Provider Data Catalog (HHS), HRSA, Census, USDA, CDC, FDA, SEC EDGAR, IRS 990 bulk, captures their metadata (publisher, license, temporal coverage, distribution URLs, data-dictionary URLs), classifies each into one source_class and one metric_coverage_class, and surfaces stale-distribution + changed-publisher drift on each refresh.

This is **Batch 0** — it MUST land before any other Priority 1 TAVR table because downstream tables (`tavr_source_readiness`, `tavr_hospital_profile`, `tavr_program_year`, etc.) read this manifest to decide which sources to ingest.

## Cross-references

- Mesh handoff: `2026-05-14-edwards-meadow-to-dk-data-fe-provision-tavr-catalog-candidate-manifest.md`
- Composite parent: `2026-05-13-edwards-meadow-to-dk-data-fe-confirm-hcs-tavr-gold-provisioning-ownership.md` (closed 2026-05-14T03:00Z)
- Edwards-meadow recommendation: `2026-05-13-benchmarking-profiling-tool-recommendation.md` §Data To Provision (L346–L630), §Catalog-driven discovery (L358)
- Data strategy: `data-researcher.md` §1 (catalog harvest)

## User Scenarios & Testing

### US-1: Operator triggers catalog harvest and gets a populated manifest (P1)

**As a** TAVR Benchmark Lab consumer, **I want** to read `hcs_gold.tavr_catalog_candidate_manifest` with the full set of Priority-1 public dataset candidates, **so that** the downstream `tavr_source_readiness` table can decide ingestion priority without re-scraping every catalog.

**Acceptance Scenarios:**

```gherkin
Given the catalog harvester has run within the configured refresh cadence
When edwards-meadow's CLI queries `hcs_gold.tavr_catalog_candidate_manifest` via the metering proxy
Then ≥90% of Priority-1 sources are present with full source metadata
  And every row carries source_class + coverage_class + use_class + grain + as_of_date + source_id + confidence + caveat_text
  And every row has grain = 'dataset_package'
  And every row's source_class is exactly one of [public_machine_readable, public_abstractable, licensed_commercial, private_or_partner]
```

### US-2: Drift detector flags stale distribution URLs and publisher changes (P2)

**As a** data steward, **I want** the harvester to report which catalog packages have had their distribution URLs change or their publisher metadata mutate since the last run, **so that** I can triage ingestion-pipeline breakage before it propagates.

**Acceptance Scenarios:**

```gherkin
Given a prior run captured catalog package X with distribution_urls = [URL_A]
When the next harvest captures the same package with distribution_urls = [URL_B]
Then the run records a drift event in `meta.catalog_drift_events` keyed by catalog_package_id
  And `tavr_catalog_candidate_manifest` row X has its `last_drift_detected_at` populated
```

### US-3: Stale candidates are not allowed to linger (P2)

**As a** TAVR Benchmark Lab maintainer, **I want** any row that has stayed in `catalog_discovered` state past the agreed review SLA flagged for triage, **so that** discovered-but-unused candidates don't accumulate forever.

**Acceptance Scenarios:**

```gherkin
Given the review SLA is 30 days
When a row's `as_of_date` is older than 30 days AND its `review_state` is still `catalog_discovered`
Then a query against `meta.table_health` for `tavr_catalog_candidate_manifest` returns a non-empty `stale_candidates` array
```

## Schema (gold layer)

```sql
CREATE TABLE IF NOT EXISTS hcs_gold.tavr_catalog_candidate_manifest (
  catalog_package_id      TEXT      PRIMARY KEY,                  -- publisher-scoped id (e.g. data.gov package name)
  slug                    TEXT      NOT NULL,
  title                   TEXT      NOT NULL,
  publisher               TEXT      NOT NULL,                     -- "CMS", "HRSA", "Census", ...
  access_level            TEXT      NOT NULL CHECK (access_level IN ('public', 'restricted', 'private')),
  license                 TEXT,                                   -- SPDX-style id or free-text
  temporal_coverage       TEXT,                                   -- "2018-01-01/2024-12-31"
  last_harvested_date     TIMESTAMPTZ NOT NULL,
  data_dictionary_url     TEXT,
  distribution_urls       JSONB     NOT NULL DEFAULT '[]'::jsonb,
  search_query            TEXT,                                   -- the query that surfaced this candidate
  source_class            TEXT      NOT NULL CHECK (source_class IN ('public_machine_readable','public_abstractable','licensed_commercial','private_or_partner')),
  coverage_class          TEXT      NOT NULL,                     -- metric coverage class per recommendation
  use_class               TEXT      NOT NULL,
  grain                   TEXT      NOT NULL DEFAULT 'dataset_package' CHECK (grain = 'dataset_package'),
  as_of_date              TIMESTAMPTZ NOT NULL,
  source_id               TEXT      NOT NULL,                     -- FK-ish to meta.source_registry where applicable
  confidence              NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  caveat_text             TEXT      NOT NULL DEFAULT '',
  review_state            TEXT      NOT NULL DEFAULT 'catalog_discovered'
                                    CHECK (review_state IN ('catalog_discovered','under_review','promoted','rejected','superseded')),
  last_drift_detected_at  TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tavr_catalog_publisher_idx ON hcs_gold.tavr_catalog_candidate_manifest (publisher);
CREATE INDEX IF NOT EXISTS tavr_catalog_source_class_idx ON hcs_gold.tavr_catalog_candidate_manifest (source_class);
CREATE INDEX IF NOT EXISTS tavr_catalog_review_state_idx ON hcs_gold.tavr_catalog_candidate_manifest (review_state) WHERE review_state != 'promoted';
```

Provenance discipline columns (`source_class`, `coverage_class`, `use_class`, `grain`, `as_of_date`, `source_id`, `confidence`, `caveat_text`) are NOT NULL — every gold write must populate them. The CHECK constraints enforce the controlled vocabulary edwards-meadow's renderer expects.

## Bronze + silver layers

- `hcs_bronze.tavr_catalog_raw` — JSONB blobs straight from each catalog API (CKAN, Socrata, custom HHS endpoints). One row per fetch event.
- `hcs_silver.tavr_catalog_packages` — normalized, deduplicated package records. Conflict resolution by `(publisher, slug)`.
- Promotion `silver → gold` happens via a SQLMesh model that enforces classification + provenance fields and skips rows missing the controlled-vocabulary columns.

## Fetcher scope

Phase 0 catalog discovery:

| Publisher | API/source | Auth | Cadence |
|---|---|---|---|
| Data.gov | CKAN package_search | none | weekly |
| CMS Data Catalog | CKAN (data.cms.gov) | none | weekly |
| HHS Provider Data Catalog | Socrata | none | weekly |
| HRSA Data Warehouse | catalog index | none | weekly |
| Census Data API | catalog endpoint | API key (low-rate) | monthly |
| USDA Data | DKAN/CKAN | none | monthly |
| CDC Data Catalog | Socrata | none | weekly |
| FDA openFDA / openFDA-catalog | none | none | weekly |
| SEC EDGAR | submissions/full-index | none | monthly |
| IRS 990 | bulk index | none | monthly |

Each fetcher writes raw response payloads to `hcs_bronze.tavr_catalog_raw` and increments `meta.refresh_log`. New-package detection runs in silver via `ON CONFLICT (publisher, slug) DO UPDATE` and emits drift events.

## Functional Requirements

- **FR-001**: The harvester MUST capture all source-required fields per the acceptance bar (≥90% completeness on Priority-1 sources).
- **FR-002**: Every gold row MUST satisfy the provenance-discipline NOT-NULL set; a partial row is refused at the SQLMesh model layer with a `caveat_text`-required error written to `meta.transform_runs`.
- **FR-003**: Stale URLs MUST surface as `last_drift_detected_at` updates plus a row in `meta.catalog_drift_events`.
- **FR-004**: The CronJob CronJob MUST publish a job-complete event with row counts to `meta.refresh_log` so edwards-meadow's `tavr-bench` suite can verify freshness.
- **FR-005**: The schema MUST be queryable by the `edwards-meadow` (alias `em`) consumer registered in PR #383 — schema `hcs_gold` is already in their allowlist.

## Success Criteria

- **SC-001**: First end-to-end run completes within 30 minutes wall-clock (bronze fetch + silver dedupe + gold promotion across all 10 publishers).
- **SC-002**: `tavr-bench run --suite dk-data-origin-readiness --env dk-data-prod` reports ≥90% of Priority-1 sources present after the first scheduled run.
- **SC-003**: No row in gold has any provenance-discipline column NULL.
- **SC-004**: Drift detector reports at least the URLs that have actually changed between runs (no false positives in a same-week re-run).

## Out of scope

- Actual ingestion of the cataloged datasets — that's `tavr_source_readiness` (Phase 1A) onwards.
- Licensed-commercial overlay catalog (`hcs_licensed.*`) — separate handoff.
- LLM-based catalog extraction — Phase 0 is structured-field harvest only (D001).

## Open questions

1. **Refresh-log scope**: should each publisher's fetcher emit its own `meta.refresh_log` row, or one composite row per harvest run? Edwards-meadow's verification reads row counts per source — leaning per-publisher.
2. **Search-query persistence**: the recommendation captures the literal search query that surfaced each candidate; should this be free-text or a structured `(field, operator, value)` triple? Going free-text for v1.

## Estimated effort

- Spec → plan: 0.5d (this doc + `/dk.plan` deepening)
- Plan → tasks: 0.5d
- Implementation: 2-3d (10 fetchers × half-day each, plus SQLMesh model + tests + verification suite hookup)
- **Total**: ~3-4 days

## Dependencies

- ✅ PR #383 — edwards-meadow consumer registered (auth path)
- ✅ Composite ownership handoff acked (provisioning contract)
- 🔄 Issue 2 backup chain verification (12:00 UTC 2026-05-14) — does not block Phase 0 work but should land first so we don't compound risk on prod IO

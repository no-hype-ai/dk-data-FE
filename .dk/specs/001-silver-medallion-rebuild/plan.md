# Implementation Plan

**Branch**: `feature/001-silver-medallion-rebuild`
**Date**: 2026-04-11
**Spec**: [spec.md](./spec.md)

## Summary

**Primary requirement**: Rebuild the dk-data silver layer on canonical entity-resolution hub tables (10 hubs across `mol_silver` / `hcs_silver` / `ind_silver`) so silver carries forward every bronze column, eliminates the 5 banned silver antipatterns, and stays inside the fixed CNPG cluster's WAL / CPU / memory / connection ceilings.

**Technical approach**: Write hub tables, identifier crosswalks, name indexes, and `resolve_*()` functions as new SQLMesh models in the existing `src/dk_data/sqlmesh/models/` tree. Bootstrap each hub via PL/pgSQL procedures that read existing bronze with chunked mid-loop COMMITs (≤50K rows / ≤200 MB WAL per chunk, `pg_sleep(0.05)` between chunks). Wrap every Python DB connection in a single `build_dsn()` helper that enforces client-side timeouts, keepalives, and `application_name`. Route long-lived pods through PgBouncer; reserve direct postgres connections for SQLMesh and PL/pgSQL procedures. Replace the 5 silver antipatterns by rewriting the 10 worst silver models in priority order (largest blast radius first). Wire free-text sources via the harmonized sibling fields the source APIs already expose — no LLM calls.

## Technical Context

| Dimension | Value |
|-----------|-------|
| Language/Version | Python 3.11+ (existing); PL/pgSQL for hub bootstrap procedures; SQL (PostgreSQL 16.4 dialect) for SQLMesh models |
| Primary Dependencies | SQLMesh ≥0.90, psycopg2-binary, Pydantic, structlog, OpenTelemetry SDK, prometheus-client (all already in `pyproject.toml`); pytest + responses for tests |
| Storage | PostgreSQL 16.4 via CloudNativePG (`postgresql.infra.svc.cluster.local:5432`, database `dk_data`); routed through PgBouncer transaction-mode (`pgbouncer.infra.svc.cluster.local:5432`) for fetcher pods; direct connection for SQLMesh/procedures |
| Testing Framework | pytest with the existing fixtures in `tests/`; SQLMesh model audits; CI grep for antipattern signatures and column-retention contract test |
| Target Platform | K3s on penguin (single node), CNPG postgres pod 2 CPU / 4 GiB hard cap, multi-tenant with `behavior_labs` and `litellm` |
| Project Type | Data platform — no web service, no REST API of its own (PostgREST exposes the silver/gold tables to consumers but is out of scope for this feature) |
| Performance Goals | SC-008 (full bootstrap ≤105 min wall clock, ≤7 GB WAL, no row lock >1 s); SC-005 (10 worst silver models complete <10 min); SC-004 (resolve functions <10 ms p99); SC-009 (multi-tenant p95 latency increase ≤10%) |
| Constraints | `max_wal_size = 4 GB` (hard ceiling — FR-021 limits dk-data to ≤2 GB WAL per transaction); `shared_buffers = 512 MB`; `work_mem ≈ 4 MB`; `max_connections = 200` shared; ZFS pool 92% full; no `pg_stat_statements`; no `auto_explain`; `restart_after_crash = off`; barman-cloud archiver flaky |
| Scale/Scope | ~25M chembl_activities rows, ~10M NPPES providers, ~12M trademarks, ~5M patents, ~3M designs, ~30M PubMed abstracts, ~17M FAERS reports already in bronze. Total bronze ≈ 100 GB. Bootstrap writes ~46M rows across the 10 hubs and their crosswalks/name indexes. |

## Constitution Check

`.dk/memory/constitution.md` does not exist. Skipping the constitution gate evaluation. The project's reliability principles documented in `.dk/memory/principles.md` and the source reliability doc are honored throughout — every FR maps to one of the 6 reliability principles or to one of the 4 entity-linking patterns.

## Project Structure

The dk-data-FE repository already has a stable layout. This feature adds new files inside that layout — no new top-level directories.

```
src/dk_data/
├── ingestion/
│   ├── fetchers/                  # Existing — connection-string fixes (FR-022, FR-027, FR-029) + 6 IP fetchers retargeted from mol_raw to ip_raw (FR-006c)
│   │   ├── uspto_patents.py       # MODIFIED — writes to ip_raw.uspto_patents
│   │   ├── uspto_ci.py            # MODIFIED — writes to ip_raw.uspto_ci
│   │   ├── uspto_trademarks.py    # MODIFIED — writes to ip_raw.uspto_trademarks
│   │   ├── epo_ops.py             # MODIFIED — writes to ip_raw.epo_patents
│   │   ├── euipo_trademarks.py    # MODIFIED — writes to ip_raw.euipo_trademarks
│   │   ├── euipo_designs.py       # MODIFIED — writes to ip_raw.euipo_designs
│   │   ├── orange_book.py         # UNCHANGED — stays in mol_raw (FDA drug↔patent crosswalk)
│   │   └── purple_book.py         # UNCHANGED — stays in mol_raw (biologic registry)
│   └── utils/
│       └── database.py            # NEW build_dsn() helper enforcing FR-022, FR-023, FR-030
├── sqlmesh/
│   └── models/
│       ├── molecules/
│       │   ├── bronze/            # Existing — untouched (FR-010)
│       │   └── silver/
│       │       ├── molecules.sql               # NEW hub
│       │       ├── molecule_identifiers.sql    # NEW crosswalk (replaces deleted identifier_mappings)
│       │       ├── molecule_names.sql          # NEW name index (replaces deleted molecule_aliases)
│       │       ├── drug_products.sql           # NEW SCD/SBD-level hub
│       │       ├── drug_product_identifiers.sql
│       │       ├── drug_product_names.sql
│       │       ├── drug_product_ingredients.sql
│       │       ├── targets.sql + target_identifiers + target_names + target_sequences
│       │       ├── companies.sql + company_identifiers + company_names
│       │       └── (rewritten enrichment models)  # bioactivity, adverse_events, clinical_trials, etc.
│       ├── ind/                           # Indication / disease / epidemiology domain
│       │   └── silver/
│       │       └── conditions.sql + condition_identifiers + condition_names
│       ├── hcs/                           # Healthcare system / CMS / provider domain
│       │   └── silver/
│       │       ├── providers.sql + provider_identifiers + provider_names
│       │       └── facilities.sql + facility_identifiers + facility_names
│       ├── hcp/                           # Healthcare professional / KOL / researcher domain
│       │   └── silver/
│       │       ├── researchers.sql + researcher_identifiers + researcher_names
│       │       ├── researcher_provider_crosswalk.sql
│       │       ├── researcher_publications.sql
│       │       └── researcher_affiliations.sql
│       └── ip/                            # Intellectual property domain
│           ├── bronze/                            # Migrated from molecules/bronze/ (FR-006d)
│           │   ├── uspto_patents.sql               # was mol_bronze.uspto_patents
│           │   ├── uspto_ci.sql                    # was mol_bronze.uspto_ci
│           │   ├── uspto_trademarks.sql            # was mol_bronze.uspto_trademarks
│           │   ├── epo_patents.sql                 # was mol_bronze.epo_patents
│           │   ├── euipo_trademarks.sql            # was mol_bronze.euipo_trademarks
│           │   ├── euipo_designs.sql               # was mol_bronze.euipo_designs
│           │   └── trademark_status_history.sql    # was mol_bronze.trademark_status_history
│           ├── silver/                             # Migrated from molecules/silver/ (FR-006e)
│           │   ├── patents.sql + patent_identifiers + patent_names    # NEW hub-architecture (replaces legacy mol_silver.patents)
│           │   ├── trademarks.sql + trademark_identifiers + trademark_names    # NEW hub-architecture
│           │   ├── designs.sql + design_identifiers + design_names    # NEW hub (renamed from euipo_designs)
│           │   ├── patent_exclusivities.sql        # was mol_silver.patent_exclusivities
│           │   └── trademark_status_changes.sql    # was mol_silver.trademark_status_changes
│           └── gold/                               # NEW — IP-specific gold models
│               └── (added by this feature or follow-ups: patent_landscape, trademark_freedom_to_operate)
└── sql/
    └── migrations/
        └── 031_silver_hub_rebuild/      # NEW
            ├── 001_meta_job_locks.sql
            ├── 002_meta_refresh_state.sql
            ├── 003_meta_linkage_conflicts.sql
            ├── 004_resolve_molecule.sql       # PL/pgSQL function
            ├── 005_resolve_drug_product.sql
            ├── 006_resolve_target.sql
            ├── 007_resolve_condition.sql
            ├── 008_resolve_company.sql
            ├── 009_resolve_provider.sql
            ├── 010_resolve_facility.sql
            ├── 011_resolve_patent.sql
            ├── 012_resolve_trademark.sql
            ├── 013_resolve_design.sql
            ├── 014_bootstrap_facilities.sql   # smallest-first
            ├── 015_bootstrap_companies.sql
            ├── 016_bootstrap_conditions.sql
            ├── 017_bootstrap_targets.sql
            ├── 018_bootstrap_molecules.sql
            ├── 019_bootstrap_drug_products.sql
            ├── 020_bootstrap_designs.sql
            ├── 021_bootstrap_patents.sql
            ├── 022_bootstrap_trademarks.sql
            └── 023_bootstrap_providers.sql    # largest last (10M NPPES rows)

tests/
├── test_silver_column_retention.py    # NEW — FR-005 contract test using SQLMesh DAG introspection
├── test_silver_antipatterns.py        # NEW — FR-020 grep for S1–S5 signatures
├── test_resolve_molecule.py           # NEW — per-resolve-function unit tests
├── test_resolve_drug_product.py
├── ...
├── test_build_dsn.py                  # NEW — FR-030 enforces single helper
└── test_meta_job_locks.py             # NEW — FR-025 concurrency test
```

## Phase 0 — Research

### Hub bootstrap order

- **Decision**: Smallest-first within dependency tiers. Tier 0 (no FK deps): facilities, companies, conditions, targets. Tier 1: molecules (depends on conditions for indications), designs (depends on companies). Tier 2: drug_products (depends on molecules for ingredients), trademarks (depends on companies). Tier 3: patents (depends on companies + molecules via Orange Book), providers (depends on facilities — last because ~10M NPPES rows).
- **Rationale**: Validates the chunked PL/pgSQL pattern on small hubs (facilities is 6K rows, companies ~10K) before tackling the 10M-row providers hub. Respects FK constraints. Fails fast if a small hub has bugs without burning 15 minutes on a large bootstrap first.
- **Alternatives considered**: (a) strict size order ignoring deps — would fail FK constraints on first run; (b) topological sort with arbitrary tie-breaking — wastes the validation opportunity that smallest-first gives us; (c) parallel bootstrap of independent tiers — more complex, harder to attribute WAL spikes during the run.

### Resolve function strictness

- **Decision**: Each `resolve_*()` function is `STABLE PARALLEL SAFE` and walks the entity-type-specific priority tree (FR-009). The trigram fallback (FR-013) returns NULL below 0.85; matches at or above 0.85 return with the computed `confidence`.
- **Rationale**: `STABLE` lets postgres cache results within a query plan. `PARALLEL SAFE` allows parallel hash joins to call the function. The 0.85 threshold matches the documented `pg_trgm` "probably the same word" boundary.
- **Alternatives considered**: (a) `IMMUTABLE` — wrong because hub data can change between calls; (b) returning the best fuzzy match always — pollutes downstream gold layer (hence the two-tier 0.85/0.95 split); (c) per-call confidence override — adds an unused parameter to every call site.

### Free-text source linking

- **Decision**: Read structured sibling fields the source APIs already provide: `openfda.unii[]`/`rxcui[]`/`product_ndc[]`/`substance_name[]` for FAERS and labels; `protocolSection.derivedSection.interventionMeshList[]`/`conditionMeshList[]` for ClinicalTrials.gov; `MeshHeadingList`/`ChemicalList` for PubMed/EuropePMC; Orange Book join for FDA-approved drug patents; precompiled WHO INN regex for medical news; `reactionmeddrapt` for FAERS reactions.
- **Rationale**: Source-API audit during the spec phase found ~80–90% of cases originally assumed to need LLM extraction are already structured. Cost analysis: $8K–30K one-time + $2.5K–10K/year for LLM coverage — does not justify the marginal lift.
- **Alternatives considered**: (a) LLM extraction via `litellm-server` — rejected on cost and the model-drift / re-extraction overhead; (b) commercial pharma pipeline DB licensing (Cortellis / Adis Insight) — deferred until a product feature requires the marginal coverage.

### Contract test data source

- **Decision**: Use SQLMesh's `Context.dag.upstream()` and `Context.get_model(name).columns_to_types` for the FR-005 contract test. No live DB. No manifest file. No SQL comment annotation.
- **Rationale**: SQLMesh already parses every model and exposes the DAG via Python API — the only source of truth that cannot drift from the actual code.
- **Alternatives considered**: (a) maintained YAML manifest — drift risk; (b) SQL comment headers — easy to forget; (c) `information_schema.columns` query — needs a live DB and produces stale results between deploys.

### Per-transaction WAL accounting

- **Decision**: Each chunked PL/pgSQL procedure calls `pg_current_wal_lsn()` at chunk start and end, computes the byte delta with `pg_wal_lsn_diff()`, and inserts a row into `meta.transform_runs (procedure_name text, chunk_position text, started_at timestamptz, ended_at timestamptz, rows_processed bigint, wal_bytes bigint)`. Operators can grep this table to verify FR-021 compliance and feed prometheus metrics.
- **Rationale**: The cluster has no `pg_stat_statements`. We need application-side WAL accounting to enforce the 2 GB ceiling.
- **Alternatives considered**: (a) parse postgres logs for checkpoint events — fragile and high latency; (b) enable `pg_stat_statements` — requires Nick to change the cluster, out of scope.

## Phase 1 — Design

Generated artifacts in this directory:

- [`data-model.md`](./data-model.md) — schemas for the 10 hubs, their crosswalks, name indexes, ingredient table, the 3 meta tables, and the 10 resolve functions
- [`contracts/`](./contracts/) — `resolve_*()` function signatures (the only "API" surface this feature exposes; PostgREST exposes the resulting silver tables but the route shapes are auto-generated and out of scope)
- [`quickstart.md`](./quickstart.md) — how to run the bootstrap locally against a CNPG instance, how to run the contract tests, how to verify a single rewritten silver model

## Complexity Tracking

| Area | Violation | Justification | Approved By |
|------|-----------|---------------|-------------|
| 10 hubs in one feature | Larger than typical | The 10 hubs are interlinked (drug_products → molecules, patents → companies + molecules, providers → facilities) so a partial cut would block silver enrichment models that join across them. Bootstrap budget (105 min / 7 GB WAL) still fits the cluster's reliability ceilings. | (autonomous) |
| Bootstrap procedures in PL/pgSQL not Python | Procedural code in the database | Required by FR-021 — Python-side row loops over 10M NPPES rows would either hold a single transaction open (failing FR-021) or commit per row (slow + lock thrashing). PL/pgSQL with mid-loop COMMITs is the only pattern that fits the WAL ceiling and the multi-tenant CPU budget. | (autonomous) |
| `meta.linkage_conflicts` audit table | Adds a new meta table not mentioned in the source docs | FR-026a requires it for crosswalk dedupe / conflict detection. Without it, a re-run that produces a different `hub_id` for the same `(source, identifier)` would silently corrupt downstream joins. | (autonomous, Phase 2 clarify) |

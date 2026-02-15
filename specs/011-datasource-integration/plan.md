# Implementation Plan: Data Source Integration

**Branch**: `011-datasource-integration` | **Date**: 2026-02-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-datasource-integration/spec.md`

## Summary

Enable 33 remaining data sources across tiers 2-4 by extending the existing molecule ingestion pipeline (Tier 2A/3: 13 sources via grouped CronJobs) and implementing new CI fetchers (Tier 4: 10 sources via individual CronJob manifests with BaseFetcher pattern). Tier 2B sources (4 credential-gated) are implemented but deferred pending credential acquisition. Broken ACC TVC source is researched and fixed or replaced.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: psycopg2-binary, Pydantic, httpx, requests, structlog, opentelemetry-sdk, pandas, feedparser (new, for RSS)
**Storage**: PostgreSQL 16.4 via CloudNativePG — schemas: `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `raw`, `staging`, `meta`, `api`
**Testing**: pytest with mocked HTTP responses (requests-mock or responses library)
**Target Platform**: Kubernetes (k3s cluster), CronJob workloads deployed via ArgoCD
**Project Type**: Backend data platform (no UI components)
**Performance Goals**: Each CronJob completes within its `activeDeadlineSeconds` (600s for small sources, 7200-14400s for large molecule batches)
**Constraints**: CronJob schedule slots must not conflict; Doppler secret sync required for credentialed sources; ArgoCD must sync successfully
**Scale/Scope**: 33 new data sources (13 molecule → grouped jobs, 10 CI → individual jobs, 4 credential-gated → deferred, 1 fix, 5 already via CI sources with query-scoped fetches)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No project-specific constitution defined (template only). No gates to evaluate. Proceeding with standard engineering practices:
- All code follows existing patterns (BaseFetcher, RawIngestionService)
- Tests required for new fetchers
- Idempotent upserts for all data loads
- Secrets via Doppler, never hardcoded

**Post-design re-check**: No violations. All new code extends existing patterns without architectural changes.

## Project Structure

### Documentation (this feature)

```text
specs/011-datasource-integration/
├── plan.md              # This file
├── research.md          # Phase 0: Architecture research
├── data-model.md        # Phase 1: Entity model
├── quickstart.md        # Phase 1: Integration guide
├── contracts/           # Phase 1: CI source API view contracts
│   └── ci-api-views.sql
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2: Task breakdown (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/dk_data/
├── ingestion/
│   ├── fetchers/              # BaseFetcher implementations (Tier 4 CI sources)
│   │   ├── base.py            # (existing) Abstract base
│   │   ├── pubmed.py          # (new) PubMed/MEDLINE fetcher
│   │   ├── openalex_ci.py     # (new) OpenAlex CI fetcher
│   │   ├── ema_regulatory.py  # (new) EMA Regulatory CI fetcher
│   │   ├── journal_rss.py     # (new) Journal RSS framework
│   │   ├── uspto_ci.py        # (new) USPTO PatentsView CI
│   │   ├── hta_bodies.py      # (new) HTA body decisions
│   │   ├── epo_ops.py         # (new) EPO Open Patent Services
│   │   ├── cochrane.py        # (new) Cochrane Library
│   │   ├── medical_news.py    # (new) Medical news aggregator
│   │   ├── sec_edgar.py       # (new) SEC EDGAR filings
│   │   └── __init__.py        # (modify) Register new fetchers
│   ├── sources/               # Loaders for CI sources
│   │   ├── pubmed.py          # (new) PubMed loader
│   │   ├── openalex_ci.py     # (new) OpenAlex CI loader
│   │   └── ...                # (new) One per CI source
│   ├── fetch_data.py          # (modify) Register CI fetchers in FETCHERS dict
│   ├── fetch_molecules.py     # (existing) Molecule CLI — source list extended via config
│   └── utils/
│       ├── validators.py      # (modify) Add CI source Pydantic models
│       └── database.py        # (existing) No changes needed
├── services/data_platform/
│   └── raw_ingestion.py       # (existing) Already has Tier 2A/3 classes
├── scripts/
│   └── catalog_refresh.py     # (modify) Add SOURCE_METADATA for all new sources
└── sql/
    ├── migrations/
    │   └── 060_ci_source_tables.sql  # (new) Raw tables for Tier 4 CI sources
    ├── seed_data_sources.sql         # (modify) Add all new source entries
    └── seed_batch_jobs.sql           # (modify) Add CI batch job entries

k8s/base/ingestion/
├── cronjob-mol-fetch-daily.yaml     # (modify) May add sources
├── cronjob-mol-fetch-weekly.yaml    # (modify) Add Tier 2A/3 weekly sources
├── cronjob-mol-fetch-monthly.yaml   # (new) Monthly molecule sources
├── cronjob-fetch-pubmed.yaml        # (new) PubMed daily
├── cronjob-fetch-openalex-ci.yaml   # (new) OpenAlex CI daily
├── cronjob-fetch-ema-reg.yaml       # (new) EMA Regulatory weekly
├── cronjob-fetch-journal-rss.yaml   # (new) Journal RSS daily
├── cronjob-fetch-uspto-ci.yaml      # (new) USPTO CI weekly
├── cronjob-fetch-hta.yaml           # (new) HTA bodies weekly
├── cronjob-fetch-epo.yaml           # (new) EPO OPS weekly
├── cronjob-fetch-cochrane.yaml      # (new) Cochrane monthly
├── cronjob-fetch-news.yaml          # (new) Medical news daily
├── cronjob-fetch-sec-edgar.yaml     # (new) SEC EDGAR daily
└── molecule-pipeline-config.yaml    # (existing) No changes

k8s/base/kustomization.yaml          # (modify) Add new CronJob resources

tests/
├── test_pubmed_fetcher.py           # (new) Per CI source
├── test_openalex_ci_fetcher.py      # (new)
├── test_ema_regulatory_fetcher.py   # (new)
├── test_molecule_sources.py         # (new) Verify Tier 2A/3 registration
└── ...                              # (new) One per CI source
```

**Structure Decision**: Extends existing project structure. Tier 4 CI sources follow the established `BaseFetcher` pattern in `src/dk_data/ingestion/fetchers/`. Tier 2A/3 molecule sources are already implemented in `raw_ingestion.py` and only need scheduling configuration and metadata.

## Implementation Strategy

### Tier 2A/3 Molecule Sources (P1 + P2): Config-Only

These sources have complete `RawIngestionService` subclasses. Implementation is:
1. Extend `mol-fetch-weekly` source list to include new weekly sources (EMA, Orange Book)
2. Create `mol-fetch-monthly` CronJob for monthly sources (BindingDB, SIDER, TDC ADMET, KEGG, TTD, PharmGKB, IMGT, CDC Vaccines, UniProt, RxNorm, DailyMed, FDA Drugs)
3. Add seed SQL entries for all 13 sources
4. Add SOURCE_METADATA entries for all 13 sources
5. The `should_refresh()` method in `RawIngestionService` already handles tiered scheduling

### Tier 4 CI Sources (P3-P6): Full Implementation

Each CI source requires the complete `/add-datasource` workflow:
1. Fetcher class extending `BaseFetcher`
2. Pydantic validator model
3. Source loader with ON CONFLICT upserts
4. SQL migration for raw table
5. Individual CronJob manifest
6. Seed SQL + catalog metadata
7. Unit tests

### CronJob Schedule (Updated)

```
Hour  Day         Job                       Source
────  ──────────  ────────────────────────  ──────────
02    Daily       mol-fetch-daily           ClinicalTrials, OpenFDA
02    Sun         fetch-cms-all             CMS + HRSA + ACC
03    Sun         mol-fetch-weekly          ChEMBL, PubChem, OpenAlex, EMA, Orange Book
04    1st quarter fetch-acc-tvc             ACC TVC
05    15th month  fetch-hrsa               HRSA Shortage Areas
06    Daily       catalog-refresh           All sources metadata
07    Daily       sqlmesh-run              All transforms
08    Daily       mol-fetch-monthly*        BindingDB, SIDER, TDC, KEGG, TTD, PharmGKB, IMGT, CDC, UniProt, RxNorm, DailyMed, FDA Drugs
10    Daily       mol-transform             Bronze→Silver→Gold
11    Daily       fetch-pubmed*             PubMed (broad ingest)
12    Daily       fetch-openalex-ci*        OpenAlex CI (broad ingest)
13    Weekly      fetch-ema-reg*            EMA Regulatory CI
13    Daily       fetch-journal-rss*        Journal RSS feeds
14    Weekly      fetch-uspto-ci*           USPTO PatentsView CI
14    Weekly      fetch-hta*               HTA bodies (NICE, G-BA, HAS, PBAC)
15    Weekly      fetch-epo*               EPO OPS patents
15    Monthly     fetch-cochrane*          Cochrane reviews
16    Daily       fetch-news*              Medical news
16    Daily       fetch-sec-edgar*         SEC EDGAR filings
```
*New CronJobs

## Complexity Tracking

No constitution violations to justify.

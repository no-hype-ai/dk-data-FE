# Implementation Plan: USPTO & EUIPO Model Datasource Integration

**Branch**: `014-uspto-euipo-model-datasource` | **Date**: 2026-02-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/014-uspto-euipo-model-datasource/spec.md`

## Summary

Integrate all 5 IP data sources (USPTO CI, USPTO Patents, EPO OPS, USPTO Trademarks, EUIPO Trademarks) into the dk-data-FE medallion architecture (raw -> bronze -> silver -> gold) via SQLMesh models, with new fetchers for trademark data, Prometheus metrics, Kubernetes CronJobs, and CI/CD test coverage.

The core problem is that existing patent data (USPTO + EPO) is stuck at the raw layer due to a broken bronze model (`bronze.uspto_patents` expects JSONB but raw table has flat columns), missing bronze models (`bronze.uspto_ci`, `bronze.epo_patents`), and an incomplete silver model (`silver.patents` only reads DrugBank). Additionally, two new trademark sources (USPTO TSDR API + EUIPO TMview/IBM Gateway) need full pipeline integration from fetcher through gold layer.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, SQLMesh, Pydantic, psycopg2-binary, requests, responses (test), structlog, OpenTelemetry, prometheus-client, kubernetes
**Storage**: PostgreSQL 16.4 (CloudNativePG cluster, `postgresql.infra.svc.cluster.local:5432`, database `dk_data`)
**Testing**: pytest + responses (mocked HTTP), Pydantic validation tests, kubectl kustomize manifest validation
**Target Platform**: Kubernetes (k3s cluster), Linux containers (Dockerfile)
**Project Type**: Single project (Python package `dk_data`)
**Performance Goals**: Incremental SQLMesh pipeline from raw to silver in <10 minutes; API rate limits respected (TSDR: 60 req/min, TMview: 30 req/min)
**Constraints**: TSDR API is lookup-only (no search by Nice Class) — requires bulk XML for initial Class 5 dataset (~200K+ records); EUIPO IBM Gateway is gated (requires registration); TMview serves as fallback
**Scale/Scope**: ~10,000 existing patent records in raw tables; ~200K+ USPTO trademarks (all active Class 5); ~200K+ EUIPO trademarks (Class 5); weekly deltas of ~500-2,000 records per trademark source

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No project-specific constitution has been ratified. The `.specify/memory/constitution.md` contains only placeholder values. No gate violations possible — proceeding to Phase 0.

**Post-Phase 1 re-check**: N/A (no constitution gates to evaluate).

## Project Structure

### Documentation (this feature)

```text
specs/014-uspto-euipo-model-datasource/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification (completed)
├── research.md          # Phase 0 output (completed)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── checklists/
│   └── requirements.md  # Spec quality checklist (completed)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── bronze-models.md
│   ├── silver-models.md
│   ├── gold-models.md
│   ├── fetchers.md
│   └── migrations.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/dk_data/
├── ingestion/
│   ├── fetchers/
│   │   ├── base.py                    # Existing BaseFetcher (no changes)
│   │   ├── uspto_ci.py                # Existing (no changes)
│   │   ├── uspto_patents.py           # Existing (no changes)
│   │   ├── epo_ops.py                 # Existing (no changes)
│   │   ├── uspto_trademarks.py        # NEW — TSDR API fetcher
│   │   └── euipo_trademarks.py        # NEW — TMview + IBM Gateway fetcher
│   ├── sources/
│   │   ├── uspto_trademarks.py        # NEW — raw loader
│   │   └── euipo_trademarks.py        # NEW — raw loader
│   ├── fetch_data.py                  # MODIFY — register new fetchers
│   └── utils/
│       └── validators.py              # MODIFY — add Pydantic models
├── services/
│   └── data_platform/
│       └── metrics.py                 # MODIFY — add IP sources to local_sources, layer_tables, raw_sources dicts
├── observability/
│   └── metrics.py                     # MODIFY — add IP_DATA_SOURCES constant only (Gauges already in data_platform/metrics.py)
├── ingestion/
│   └── transform_molecules.py         # MODIFY — add IP models to LAYER_MODELS dict (T035)
├── sql/
│   ├── seed_data_sources.sql          # MODIFY — add trademark entries
│   └── migrations/
│       ├── 071_uspto_trademarks_raw.sql     # NEW
│       ├── 072_euipo_trademarks_raw.sql     # NEW
│       └── 073_trademark_status_history.sql # NEW
└── sqlmesh/
    └── models/
        └── molecules/
            ├── bronze/
            │   ├── uspto_patents.sql   # MODIFY — fix JSONB -> flat column
            │   ├── uspto_ci.sql        # NEW
            │   ├── epo_patents.sql     # NEW
            │   ├── uspto_trademarks.sql # NEW
            │   └── euipo_trademarks.sql # NEW
            ├── silver/
            │   ├── patents.sql         # MODIFY — UNION ALL 4 sources
            │   └── trademarks.sql      # NEW
            └── gold/
                └── molecule_profile.sql # MODIFY — add IP trademark section

k8s/
└── base/
    └── ingestion/
        ├── cronjob-fetch-uspto-trademarks.yaml  # NEW
        └── cronjob-fetch-euipo.yaml             # NEW

tests/
├── test_euipo_trademarks_fetcher.py   # NEW — ~12 tests
├── test_uspto_trademarks_fetcher.py   # NEW — ~14 tests
├── test_bronze_model_contracts.py     # NEW — contract tests for all bronze models
└── test_silver_model_contracts.py     # NEW — contract tests for silver models
```

**Structure Decision**: Single project structure. All new code follows the existing patterns in `src/dk_data/ingestion/` (fetchers, sources, validators) and `src/dk_data/sqlmesh/models/molecules/` (bronze, silver, gold). No new top-level directories needed.

### File Change Summary

| Category | New Files | Modified Files |
|----------|-----------|----------------|
| Fetchers | 2 (uspto_trademarks, euipo_trademarks) | 1 (fetch_data.py) |
| Loaders | 2 (sources/uspto_trademarks, euipo_trademarks) | 0 |
| Validators | 0 | 1 (validators.py — add 2 Pydantic models) |
| Migrations | 3 (071, 072, 073) | 0 |
| SQLMesh Bronze | 4 (uspto_ci, epo_patents, uspto_trademarks, euipo_trademarks) | 1 (bronze.uspto_patents fix) |
| SQLMesh Silver | 1 (trademarks.sql) | 1 (patents.sql UNION) |
| SQLMesh Gold | 0 | 1 (molecule_profile.sql IP section) |
| Metrics | 0 | 2 (services/data_platform/metrics.py + observability/metrics.py) |
| Seed Data | 0 | 1 (seed_data_sources.sql) |
| K8s CronJobs | 2 (trademarks CronJobs) | 1 (kustomization.yaml) |
| Fetcher Registry | 0 | 2 (fetchers/__init__.py + sources/__init__.py) |
| Tests | 4 (2 fetcher + 2 contract) | 0 |
| Transform | 0 | 1 (transform_molecules.py — add IP models to LAYER_MODELS) |
| **Total** | **18** | **12** |

## Complexity Tracking

> No Constitution Check violations to justify (constitution is unfilled template).

N/A

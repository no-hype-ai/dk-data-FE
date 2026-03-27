# Implementation Plan: CMS PUF & Platform Data Reconciliation

**Branch**: `019-cms-puf-platform-reconciliation` | **Date**: 2026-03-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/019-cms-puf-platform-reconciliation/spec.md`

---

## Summary

Reconcile 28 CMS PUF file-based sources and 6 API-based regulatory/clinical sources against the main-branch canonical ingestion architecture. Expand the medallion pipeline with HCS and additional mol models. Port 7 agents from the abandoned 016 branch. Add a Data Tools Gateway API router, an Agents API router, and eliminate the `xenon.publication_evidence` dependency from `mol_gold.trial_outcomes`. All changes delivered as a single consolidated migration (085) against current main-branch schema state.

---

## Technical Context

**Language/Version**: Python 3.11+ (`requires-python = ">=3.11"` in `pyproject.toml`)
**Primary Dependencies**: FastAPI 0.109+, SQLMesh >=0.90, psycopg2-binary, pandas, requests + urllib3 (retry), tenacity, loguru, anthropic SDK (LiteLLM proxy routing), kubernetes client
**Storage**: PostgreSQL 16 (CloudNativePG in K3s). Schemas: `mol_raw`, `hcs_raw`, `mol_bronze`, `hcs_bronze`, `mol_silver`, `hcs_silver`, `mol_gold`, `hcs_gold`, `meta`
**Testing**: pytest + `responses` library for mocked HTTP fetcher tests; `tests/test_agents/` for agent tests
**Target Platform**: K3s cluster (penguin/krang), CronJobs via ArgoCD GitOps; local dev via docker compose
**Performance Goals**: SC-011 — backfill completes within 10 minutes per source; SC-002 — duplicate file run completes with zero inserts
**Constraints**: BaseFetcher constructor is `__init__(self, data_dir=None)` — no `params`, no manifest; all LLM calls via LiteLLM proxy; no direct provider API calls; PostgREST raw schemas never exposed
**Scale/Scope**: 28 CMS bulk file sources (annual CSV, up to ~2GB each), 6 API sources (incremental daily/weekly), 7 agents (monthly + on-demand), 21 SQLMesh models

---

## Constitution Check

*The `.specify/memory/constitution.md` is an unpopulated template — no project-specific gates defined. The following gates are derived from observed codebase patterns and spec requirements.*

| Gate | Status | Notes |
|---|---|---|
| All new fetchers extend `BaseFetcher` | REQUIRED | Verified pattern across all existing fetchers |
| All new sources in `SOURCES` dict | REQUIRED | FR-015; existing dispatch requires it |
| `log_to_meta()` called after every run | REQUIRED | FR-013; existing infra enforces no silent runs |
| No direct LLM provider calls in agents | REQUIRED | FR-025; LiteLLM proxy only |
| Raw schemas never in PostgREST exposure | REQUIRED | FR-024b; clarification Q2 |
| `trial_outcomes.sql` removes xenon reference | REQUIRED | FR-024a, FR-033 |
| Single consolidated migration (085) | REQUIRED | FR-020 |
| All existing tests pass | REQUIRED | FR-023, SC-006 |
| New fetcher tests cover happy path + hash-skip | REQUIRED | SC-005 |

All gates passable — no violations.

---

## Project Structure

### Documentation (this feature)

```text
specs/019-cms-puf-platform-reconciliation/
├── plan.md              # This file
├── research.md          # Phase 0 — research findings
├── data-model.md        # Phase 1 — entity model
├── quickstart.md        # Phase 1 — local dev guide
├── contracts/
│   └── api.md           # Phase 1 — API endpoint contracts
├── checklists/
│   └── requirements.md  # Quality checklist
└── tasks.md             # Phase 2 — created by /speckit.tasks
```

### Source Code

```text
src/dk_data/
├── ingestion/
│   ├── fetchers/
│   │   ├── base.py                          # EXISTING — extend for per-source retry config
│   │   ├── cms_part_d_spending.py           # NEW × 28 CMS PUF fetchers
│   │   ├── cms_part_b_spending.py
│   │   ├── cms_open_payments.py
│   │   ├── cms_nppes.py
│   │   ├── cms_inpatient_puf.py             # (separate from existing cms_inpatient.py)
│   │   ├── cms_physician_puf.py
│   │   ├── cms_hospital_general_info.py
│   │   ├── cms_medicare_advantage.py
│   │   ├── cms_medicaid_drug_spending.py
│   │   ├── cms_dme_puf.py
│   │   ├── cms_home_health.py
│   │   ├── cms_hospice_puf.py
│   │   ├── cms_snf_puf.py
│   │   ├── cms_outpatient_puf.py
│   │   ├── cms_referring_providers.py
│   │   ├── cms_ordering_providers.py
│   │   ├── cms_lab_services.py
│   │   ├── cms_imaging_puf.py
│   │   ├── cms_mental_health_puf.py
│   │   ├── cms_opioid_puf.py
│   │   ├── cms_telehealth_puf.py
│   │   ├── cms_geographic_variation.py
│   │   ├── cms_chronic_conditions.py
│   │   ├── cms_dual_eligible.py
│   │   ├── cms_enrollment_puf.py
│   │   ├── cms_claim_type_puf.py
│   │   ├── cms_utilization_puf.py
│   │   ├── europepmc.py                     # NEW — mol_raw API source
│   │   └── nih_reporter.py                  # NEW — mol_raw API source
│   ├── sources/
│   │   ├── cms_part_d_spending.py           # NEW × 28 loaders
│   │   ├── ... (27 more cms_*.py loaders)
│   │   ├── europepmc.py                     # NEW
│   │   └── nih_reporter.py                  # NEW
│   └── main.py                              # EXISTING — add 28+2 SOURCES entries, per-source retry config
│
├── agents/
│   ├── base_agent.py                        # NEW — LiteLLM-routing base class
│   ├── service_line_inference.py            # NEW
│   ├── idn_hierarchy.py                     # NEW
│   ├── referral_network.py                  # NEW
│   ├── contact_verification.py             # NEW
│   ├── staffing_decomposition.py           # NEW
│   ├── equipment_inventory.py              # NEW
│   └── publication_evidence_extractor.py   # NEW — writes to mol_silver.publication_evidence
│
├── api/routes/
│   ├── data_tools.py                        # NEW — /api/v1/data-tools router
│   └── agents.py                            # NEW — /api/v1/agents router
│
├── services/data_tools/
│   ├── registry.py                          # NEW — tool registry service
│   ├── data_registry.py                     # NEW — source freshness checks
│   └── adapters/                            # NEW — 27 source adapter files
│       ├── cms_part_d.py
│       └── ... (26 more)
│
├── sqlmesh/models/
│   ├── hcs/                                 # NEW directory tree
│   │   ├── bronze/
│   │   │   ├── cms_part_d_spending.sql
│   │   │   ├── cms_part_b_spending.sql
│   │   │   ├── cms_open_payments.sql
│   │   │   ├── cms_nppes.sql
│   │   │   ├── cms_inpatient_puf.sql
│   │   │   ├── cms_physician_puf.sql
│   │   │   └── cms_hospital_general_info.sql
│   │   ├── silver/
│   │   │   └── cms_drug_market.sql
│   │   └── gold/
│   │       └── cms_drug_market_profile.sql
│   └── molecules/
│       ├── bronze/
│       │   ├── europepmc.sql                # NEW
│       │   └── nih_reporter.sql             # NEW
│       ├── silver/
│       │   ├── ema_regulatory.sql           # NEW — entity-linked from mol_bronze.ema_regulatory
│       │   ├── drug_spending.sql            # NEW — Part D + Part B UNION
│       │   └── publication_evidence.sql     # NEW — INCREMENTAL_BY_UNIQUE_KEY
│       └── gold/
│           ├── trial_outcomes.sql           # EXISTING — update to remove xenon reference + fix grain
│           └── market_summary.sql           # NEW
│
└── sql/migrations/
    └── 085_cms_puf_platform_reconciliation.sql  # NEW — single consolidated delta migration

k8s/apps/cronjobs/base/
├── cronjob-fetch-cms-part-d.yaml            # NEW × 28 CMS CronJobs
├── cronjob-fetch-cms-part-b.yaml
├── cronjob-fetch-cms-open-payments.yaml
├── cronjob-fetch-cms-nppes.yaml
├── cronjob-fetch-cms-inpatient-puf.yaml
├── cronjob-fetch-cms-physician-puf.yaml
├── cronjob-fetch-cms-hospital-general.yaml
└── ... (21 more cms-* CronJobs)

monitoring/provisioning/alerts/
└── pipeline-source-failures.yaml           # NEW — Grafana alert: ≥3 consecutive failures

tests/
├── test_cms_part_d_fetcher.py              # NEW × 28+ fetcher tests
├── ... (27 more test_cms_*.py)
├── test_europepmc_fetcher.py               # NEW
├── test_nih_reporter_fetcher.py            # NEW
├── test_publication_evidence_agent.py      # NEW
├── test_data_tools_gateway.py              # NEW
└── test_agents_router.py                   # NEW
```

**Structure Decision**: Single Python package (`src/dk_data/`). New code is added within the existing package structure. No new top-level packages introduced. HCS domain models added as a new SQLMesh subdirectory (`models/hcs/`) parallel to `models/molecules/`.

---

## Complexity Tracking

No constitution violations. All patterns follow existing codebase conventions.

---

## Phase 0: Research Findings Summary

Full findings in [research.md](./research.md). Key decisions:

1. **BaseFetcher retry**: Already implemented via `urllib3.Retry(total=3, backoff_factor=1)`. Per-source config requires ~15 lines in `main.py` to read `max_retries`/`retry_base_delay_seconds` from `SOURCES` entry and reconfigure the session.

2. **trial_outcomes.sql**: Active on main, already references `xenon.publication_evidence`. Must be updated to reference `mol_silver.publication_evidence`. Grain must be extended to include `endpoint_name`.

3. **SOURCES file-based shape**: File-based sources have no `fetcher` key — correct per existing pattern.

4. **Migration number**: 085 (next after 084 on main).

5. **PostgREST**: `PGRST_DB_SCHEMAS` env var; add `hcs_bronze`, `hcs_silver`, `hcs_gold`.

6. **Grafana alert**: Provisioning file at `monitoring/provisioning/alerts/`.

7. **Agents directory**: Empty on main — all 7 must be written fresh, starting with `base_agent.py`.

8. **HCS SQLMesh path**: New `src/dk_data/sqlmesh/models/hcs/` directory.

9. **Existing bronze**: `ema.sql`, `cochrane_reviews.sql`, `drugbank.sql`, `sec_edgar.sql` exist — verify namespace alignment before writing new models.

---

## Phase 1: Design Summary

### Data Model

Full entity definitions in [data-model.md](./data-model.md).

**New tables added by migration 085**:
- `hcs_raw.cms_part_d_spending`, `cms_part_b_spending`, `cms_open_payments`, `cms_nppes`, `cms_inpatient_puf`, `cms_physician_puf`, `cms_hospital_general_info` (+ 21 more)
- `mol_silver.publication_evidence` (UNIQUE on `content_hash`)
- `mol_silver.physician_payments`
- `mol_silver.research_grants`
- `mol_silver.agent_quarantine`
- `meta.data_sources` INSERT rows for all 28 new CMS + 6 API sources

**Modified**:
- `mol_gold.trial_outcomes` — remove `xenon.publication_evidence` reference; fix grain; update CTE to `mol_silver.publication_evidence`

### API Contracts

Full contracts in [contracts/api.md](./contracts/api.md).

**New endpoints**:
- `GET /api/v1/data-tools/registry`
- `POST /api/v1/data-tools/backfill`
- `GET /api/v1/data-tools/{source_name}/status`
- `GET /api/v1/agents`
- `POST /api/v1/agents/{agent_id}/run`
- `GET /api/v1/agents/{agent_id}/runs`
- `GET /api/v1/agents/quarantine`

### Implementation Order

Follows spec Implementation Order section:

1. **Migration 085** — audit 016 migrations vs main schema; write delta-only; apply to staging; verify `test_migration_runner.py` passes
2. **CMS PUF fetchers + loaders** (28 sources) — file-based pattern; hash-skip; register in `SOURCES`; register in `meta.data_sources` via migration
3. **API sources** — EuropePMC, NIH Reporter (new); EMA, Cochrane, DrugBank, PubChem (verify existing + extend if needed)
4. **Market summary silver view** — after CMS and EMA verified end-to-end
5. **BaseFetcher per-source retry config** — extend `main.py` to read `max_retries`/`retry_base_delay_seconds` from SOURCES
6. **Agent system** — `base_agent.py` first; then all 7 agents; quarantine table; `agents.py` router
7. **Data Tools Gateway** — `registry.py`, `data_registry.py`, 27 adapters, `data_tools.py` router
8. **`mol_silver.publication_evidence`** — migration creates table; publication evidence extractor writes to it; update `trial_outcomes.sql` to remove xenon; run SQLMesh to verify
9. **SQLMesh HCS models** — bronze (7) → silver (1) → gold (1); SQLMesh run validates
10. **SQLMesh mol additions** — `ema_regulatory.sql`, `drug_spending.sql` silver; `market_summary.sql` gold
11. **CronJob manifests** — 28 CMS + 2 API source CronJobs; follow existing manifest template
12. **PostgREST schema exposure** — update `PGRST_DB_SCHEMAS` to add `hcs_bronze`, `hcs_silver`, `hcs_gold`
13. **Grafana alert** — `monitoring/provisioning/alerts/pipeline-source-failures.yaml`
14. **SEC EDGAR** — verify/extend existing fetcher; add silver keyword-flag transformation

### Quickstart

See [quickstart.md](./quickstart.md) for local dev, testing, and deployment commands.

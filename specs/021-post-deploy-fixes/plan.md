# Implementation Plan: Post-Deployment Fixes, SQL Audit & Silver Gap Closure

**Branch**: `021-post-deploy-fixes` | **Spec**: [spec.md](./spec.md)

---

## Summary

Post-deployment audit and remediation after prod image promotion `prod-85e01aa`. Work expanded across six areas: (1) credential mis-placement and dead-source retirement, (2) systematic source catalogue hardening across ~98 sources, (3) WHO ICD fetcher rewrite, (4) full SQLMesh pipeline SQL audit fixing 26 bugs found in audits #175 and #176, (5) silver gap closure for 7 dead-end bronze sources, and (6) operational improvements to the backfill orchestrator.

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: psycopg2-binary, requests + urllib3, SQLMesh ≥0.90, Doppler CLI, kubectl/ArgoCD
**Storage**: PostgreSQL 16 (CloudNativePG). 7 new silver tables; 1 silver table deleted; 1 file renamed.
**Secrets**: Doppler project `dk-data-applications/prd` — all CronJob env vars sourced here
**Target Platform**: K3s cluster (penguin/krang), namespaces `dk-data-staging` / `dk-data-prod`
**Constraints**: No cluster-direct changes — all fixes via git push + ArgoCD sync. EPO credential update via Doppler CLI only.
**Scale/Scope**: ~98 sources; 1 retired (DDInter); 26 SQL bugs fixed; 7 silver models created; 2 orchestrator improvements

---

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| No cluster-direct changes | PASS | All fixes via git + Doppler CLI only |
| Dead source retired via manifest removal | PASS | `cronjob-fetch-cms-ddinter.yaml` removed |
| Retired fetcher code fully removed | PASS | No orphaned imports |
| Bronze model retained with retirement comment | PASS | Historical data in `hcs_raw.cms_ddinter` preserved |
| All fetchers with absent keys exit 0 | PASS | `source_unavailable` path in `main.py` |
| Credential gap tracked in GitHub issue | PASS | Issue #170 — USPTO blocked |
| EPO keys in correct Doppler project | PASS | Updated via `doppler secrets set` |
| All grain violations resolved | PASS | 10 silver models fixed with DISTINCT ON |
| No FULL models with `processed_to_silver` filter | PASS | `patent_exclusivities` filter removed |
| All bronze dead-ends have silver coverage | PASS | 7 new silver models; `cms_ddinter` excluded (retired) |
| Duplicate model removed | PASS | `mol_silver.healthcare_facilities` deleted |
| WHO ICD fetcher uses live API with dynamic discovery | PASS | No hardcoded entity IDs |

---

## Project Structure

### Documentation

```text
specs/021-post-deploy-fixes/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Audit findings + decisions
├── data-model.md        # Schema changes and new models
├── quickstart.md        # Verification guide
├── tasks.md             # Completed task list (T001–T076)
├── checklists/
│   └── requirements.md  # Spec quality validation
└── contracts/
    └── doppler-secrets.md  # Required keys in dk-data-applications/prd
```

### Source Code

```text
src/dk_data/ingestion/
├── fetchers/
│   ├── who_icd.py              # Rewritten: dynamic discovery, recursive walker, live API URL
│   ├── euipo_trademarks.py     # Fixed: IBM Gateway token URL
│   └── [~96 others audited]   # Rate limits, pagination caps reviewed
├── sources/
│   └── __init__.py             # Removed: 'cms_ddinter'
├── initial_backfill.py         # retry_with_backoff + mark_job_success per source
└── main.py                     # Prometheus server start; batch_size in _INTERNAL_KWARGS; UTC datetime

src/dk_data/sqlmesh/models/
├── molecules/
│   ├── bronze/
│   │   ├── _external_sources.yaml  # Added: mol_raw.websearch
│   │   └── who_icd.sql             # title->@value; coding_hint
│   └── silver/
│       ├── orange_book.sql          # canonical_name fix
│       ├── healthcare_facilities.sql # DELETED (duplicate)
│       ├── protein_structures.sql   # identifier_type fix
│       ├── proteins.sql             # identifier_type fix
│       ├── ema_regulatory.sql       # LATERAL alias join
│       ├── imgt.sql                 # DISTINCT ON (pdb_code)
│       ├── cochrane_reviews.sql     # DISTINCT ON + grain
│       ├── nice_hta.sql             # DISTINCT ON + guard
│       ├── ttd.sql                  # DISTINCT ON + guard
│       ├── drug_spending.sql        # STRING_AGG brnd_name
│       ├── patent_exclusivities.sql # processed_to_silver filter removed
│       ├── molecule_targets.sql     # exact target name match
│       ├── icd_codes.sql            # parent_code fix; coding_hint
│       └── ema_regulatory_docs.sql  # NEW
├── hcs/
│   └── silver/
│       ├── cms_ndc.sql              # DISTINCT ON + guard
│       ├── cms_drug_market.sql      # Part B grain fix
│       ├── cms_formulary.sql        # DISTINCT ON
│       ├── cms_pecos.sql            # DISTINCT ON
│       ├── cms_dmepos.sql           # DISTINCT ON
│       ├── cms_chow.sql             # DISTINCT ON
│       ├── cms_hospital_affiliation.sql  # DISTINCT ON
│       ├── cms_cost_reports_puf_lines.sql  # NEW
│       ├── cms_hospital_info.sql    # NEW
│       ├── cms_physician_puf_services.sql  # NEW
│       ├── cms_post_acute.sql       # NEW
│       ├── cms_stabilis.sql         # NEW
│       └── cms_usp.sql              # NEW
└── ind/
    └── silver/
        ├── indication_epidemiology.sql  # DELETED (renamed)
        └── epidemiology.sql             # RENAMED from indication_epidemiology.sql

k8s/apps/cronjobs/base/
└── kustomization.yaml   # Removed cronjob-fetch-cms-ddinter.yaml
```

---

## Implementation Phases

### Phase 1: Cluster Diagnosis (Completed)

Investigated prod cluster via Proxmox API → QEMU guest agent exec on k3s-master-1 (VMID 200, node `penguin`). Key findings: EPO 401 (credential mis-placement); CMS PUF sources scheduled for April 2026; all other issues self-healing.

### Phase 2: Credential Audit (Completed)

`doppler secrets --project dk-data-applications --config prd` audit. EPO keys updated. USPTO blocked by ID.me (Issue #170). DrugBank key intentionally empty.

### Phase 3: DDInter Retirement (Completed — branch `020`, merged)

Source TCP-unreachable since March 2026. Fetcher, loader, SOURCES entry, and CronJob manifest removed. Bronze model retained with retirement comment.

### Phase 4: Source Catalogue Hardening (Completed)

- `034d9fc` — Rate limits, pagination, backfill caps across all fetchers
- `af9f1de` — Complete audit: auth tokens, rate limits, skip sources
- `71930ed` — NICE header fix; IMGT rewritten to bulk FASTA
- `139e334` — CMS PUF dynamic multi-year backfill via catalog UUID discovery

### Phase 5: WHO ICD Fetcher Rewrite (Completed)

ICD-10 endpoint was dead (`apps.who.int` returned HTML). ICD-11 had hardcoded entity IDs that returned 404s. Complete rewrite:
- `_discover_top_chapters(base_url)` — fetches linearization root, reads `child` array
- `_walk_icd10_node(node_id, seen, remaining)` — recursive 4-level tree traversal
- Single `_get_token()` method shared by ICD-10 and ICD-11
- Bronze `who_icd.sql` updated: `title->'@value'` extraction, `coding_hint` column
- Silver `icd_codes.sql` updated: correct `parent_code` derivation for ICD-10 only

### Phase 6: SQL Model Audit #175 — 26 Bug Fixes (Completed)

Full audit of all 98 sources across the medallion pipeline. Bugs fixed:
- **Critical (6)**: Wrong column names (`inn_name`, `preferred_name`), wrong bronze table names, stale SKIP_SOURCES entries, wrong `identifier_type` values, broken molecule linkage in gold financial model
- **High (8)**: Wrong JSON key in gold, 3× DISTINCT ON missing on silver models, 2× grain violations from brand grouping, loose target matching
- **Medium (4)**: Fan-out in ema_regulatory + imgt, FULL model filter anti-pattern, file name mismatch
- **Low (4)**: Missing Prometheus server, batch_size kwarg leak, UTC datetime, retry + success metrics

### Phase 7: SQL Model Audit #176 — Remaining Gaps (Completed)

- S1: `cms_drug_market` Part B CTE grain fix (carry-forward from H7)
- S2: Deleted duplicate `mol_silver.healthcare_facilities`
- S3: `mol_silver.imgt` DISTINCT ON (carry-forward from M2)
- S6: Renamed `indication_epidemiology.sql` → `epidemiology.sql`
- S9: Added `mol_raw.websearch` to `_external_sources.yaml`
- 5 additional DISTINCT ON fixes: `cms_formulary`, `cms_pecos`, `cms_dmepos`, `cms_chow`, `cms_hospital_affiliation`

### Phase 8: Dead-End Bronze → Silver Promotion (Completed)

7 bronze tables with no silver consumer. Linkage strategy for each:

| Source | Linkage |
|--------|---------|
| `cms_cost_reports_puf_lines` | provider_id → cms_hospital_general_info (DISTINCT ON) |
| `cms_hospital_info` | Pass-through (IS the reference data) |
| `cms_physician_puf_services` | NPI → cms_nppes (DISTINCT ON) + hcpcs_code → hcpcs_molecule_bridge (LATERAL) |
| `cms_post_acute` | ccn → cms_hospital_general_info (DISTINCT ON) |
| `cms_stabilis` | drug_a + drug_b → molecule_aliases (LATERAL LIMIT 1 each) |
| `cms_usp` | rxcui → identifier_mappings (LATERAL LIMIT 1) + branded_name → molecule_aliases |
| `ema_regulatory` | active_substance → molecules canonical + alias (LATERAL LIMIT 1) |

### Phase 9: Operational Improvements (Completed)

- `initial_backfill._fetch_one`: `run_ingestion` wrapped with `@retry_with_backoff(max_attempts=3, initial_delay=30, max_delay=120)`
- `initial_backfill._fetch_one`: `mark_job_success(f'backfill_fetch_{source}')` on success/partial

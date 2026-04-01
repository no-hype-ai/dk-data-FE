# Tasks: Post-Deployment Fixes, SQL Audit & Silver Gap Closure

**Branch**: `021-post-deploy-fixes` | **Status**: Completed

---

## Phase 1: Cluster Diagnosis

- [x] T001 Connect to prod cluster via Proxmox API → QEMU guest agent exec on k3s-master-1 (VMID 200, node `penguin`)
- [x] T002 [P] Identify pods running old image `prod-61e05d7` vs new `prod-85e01aa`
- [x] T003 [P] Confirm datetime offset bug is fixed in new image (PR #159)
- [x] T004 [P] Identify EPO 401 as the only actionable cluster error (not a self-healing artifact)
- [x] T005 Check pg-backup configmap state — confirmed self-healing after ArgoCD sync

---

## Phase 2: Credential Audit

- [x] T006 Run `doppler secrets --project dk-data-applications --config prd` — full key inventory
- [x] T007 [P] Cross-reference Doppler keys against all CronJob `secretKeyRef` entries
- [x] T008 [P] Cross-reference fetcher `os.environ.get()` calls against CronJob manifests
- [x] T009 Identify EPO keys as CHANGEME placeholders in correct project, real values in `dk-data-fe/prd`
- [x] T010 Update EPO keys via `doppler secrets set --project dk-data-applications --config prd`
- [x] T011 Identify USPTO keys as CHANGEME — registration blocked by ID.me (non-US)
- [x] T012 Create GitHub issue #170 — USPTO API key registration blocker
- [x] T013 [P] Verify DrugBank graceful-skip: `source_unavailable` exit 0 in `main.py` line 1342
- [x] T014 [P] Verify USPTO Patents graceful-skip: `source_unavailable` when key absent
- [x] T015 [P] Verify USPTO Trademarks graceful-skip: empty batch on 401, proceeds without crash

---

## Phase 3: DDInter Retirement (branch `020`, merged to main)

- [x] T016 Confirm ddinter.scbdd.com and ddinter2.scbdd.com are TCP-unreachable
- [x] T017 Confirm zero downstream silver/gold consumers of DDInter data
- [x] T018 Remove `src/dk_data/ingestion/fetchers/cms_ddinter.py`
- [x] T019 Remove `src/dk_data/ingestion/sources/cms_ddinter.py`
- [x] T020 Remove `cms_ddinter` from `sources/__init__.py`
- [x] T021 Remove DDInter `SOURCES` entry and imports from `main.py`
- [x] T022 Remove `cronjob-fetch-cms-ddinter.yaml` from `k8s/apps/cronjobs/base/kustomization.yaml`
- [x] T023 Add retirement comment to `hcs_bronze/cms_ddinter.sql` (model retained for historical data)
- [x] T024 Merge to main via PR — ArgoCD prunes live CronJob on next sync

---

## Phase 4: Source Catalogue Hardening

- [x] T025 [P] Audit EUIPO IBM Gateway token URL — fix to `https://euipo.europa.eu/cas-server-webapp/oidc/accessToken`
- [x] T026 [P] Confirm USPTO ODP migration already applied in #159 (`api.uspto.gov`)
- [x] T027 [P] Fix NICE API header name
- [x] T028 [P] Rewrite IMGT fetcher to use official bulk FASTA endpoint
- [x] T029 API rate limits and backfill caps — systematic review of all ~90 sources (`034d9fc`)
- [x] T030 Complete audit of all ~90 sources: auth tokens, rate limits, skip sources (`af9f1de`)
- [x] T031 CMS PUF dynamic multi-year backfill via catalog UUID discovery (`139e334`)

---

## Phase 5: Documentation & Tracking

- [x] T032 Create GitHub issue #169 — EPO Doppler project mis-placement (closed: fixed via CLI)
- [x] T033 Revert unnecessary `doppler-secret-epo.yaml` (correct fix is Doppler UI, not new manifest)
- [x] T034 Create specs/021-post-deploy-fixes/ retrospec folder (this document)
- [x] T035 Document HCS bronze/silver pipeline gap — `job-initial-backfill` never run post-PR #149

---

## Phase 6: WHO ICD Fetcher Rewrite (#175 prerequisite)

- [x] T036 Fix dead ICD-10 API URL: `apps.who.int/…/JsonGetDescendants` → `id.who.int/icd/release/10/2019`
- [x] T037 Remove all hardcoded ICD-11 entity IDs (were stale/404); replace with dynamic chapter discovery via `_discover_top_chapters(base_url)`
- [x] T038 Add `_walk_icd10_node` recursive walker — traverses full 4-level ICD-10 tree (chapter → block → 3-char → 4-char leaf)
- [x] T039 Rename `_get_icd11_token` → `_get_token`; use same OAuth2 token for ICD-10 and ICD-11
- [x] T040 Fix no-credentials path: raise `RuntimeError` with sign-up URL instead of silently returning 0 records with `status: success`
- [x] T041 Fix `mol_bronze.who_icd.sql`: use `response_body->'title'->>'@value'` (not flat `description`); add `coding_hint` column
- [x] T042 Fix `mol_silver.icd_codes.sql`: correct `parent_code` derivation — only derive for ICD-10 4-char codes via `split_part(icd_code, '.', 1)`; add `coding_hint` passthrough

---

## Phase 7: Audit #4 (#175) — SQL Model Bug Fixes

### Critical

- [x] T043 C1: Fix `mol_silver.orange_book.sql` — replace `m.inn_name`/`m.preferred_name` with `m.canonical_name` (those columns don't exist on `mol_silver.molecules`)
- [x] T044 C2: Fix `mol_silver.healthcare_facilities.sql` — wrong bronze table names: `cms_inpatient` → `cms_inpatient_puf`, `cms_hospital_info` → `cms_hospital_general_info`, `cms_cost_reports` → `cms_cost_reports_puf`
- [x] T045 C3: Remove `cms_usp`, `cms_stabilis`, `cms_dual_eligible` from `SKIP_SOURCES` in `initial_backfill.py` — all have working automated fetchers; stale comments were wrong
- [x] T046 C4: Fix `mol_silver.protein_structures.sql` — `identifier_type = 'pdb_ligand'` → `'pubchem_cid'` (pdb_ligand never populated in `identifier_mappings`)
- [x] T047 C5: Fix `mol_silver.proteins.sql` — `identifier_type = 'uniprot'` → `'uniprot_id'` (canonical value in `identifier_mappings`)
- [x] T048 C6: Fix `mol_gold.financial_summary.sql` — company_name ≠ canonical_name; bridge through `mol_silver.clinical_trials.lead_sponsor` instead

### High

- [x] T049 H1: Fix `mol_gold.company_pipeline.sql` — JSON key `intervention->>'interventionType'` → `intervention->>'type'`
- [x] T050 H2: Fix `mol_silver.cochrane_reviews.sql` — add `DISTINCT ON (b.review_id)` + `grain review_id` declaration
- [x] T051 H3: Fix `mol_silver.nice_hta.sql` — add `DISTINCT ON (b.guidance_id)` + alias join guard
- [x] T052 H4: Fix `mol_silver.ttd.sql` — add `DISTINCT ON (b.ttd_id)` + alias join guards
- [x] T053 H5: Fix `hcs_silver.cms_ndc.sql` — add `DISTINCT ON (b.product_ndc)` + alias join guard
- [x] T054 H6: Fix `mol_silver.drug_spending.sql` — remove `brnd_name` from Part D `GROUP BY`; aggregate with `STRING_AGG`
- [x] T055 H7: Fix `hcs_silver.cms_drug_market.sql` — Part B CTE: remove `hcpcs_cd`/`mftr_name` from `GROUP BY`; aggregate both with `STRING_AGG` to match grain `(generic_name, _source_year)`
- [x] T056 H8: Fix `mol_silver.molecule_targets.sql` — DrugBank target join: `strpos(LOWER(t.target_name), LOWER(tgt->>'name')) > 0` → exact `LOWER(t.target_name) = LOWER(tgt->>'name')`

### Medium

- [x] T057 M1: Fix `mol_silver.ema_regulatory.sql` — replace open `LEFT JOIN mol_silver.molecule_aliases` with `LEFT JOIN LATERAL (... LIMIT 1)` to prevent fan-out on alias matches
- [x] T058 M2: Fix `mol_silver.imgt.sql` — add `DISTINCT ON (b.pdb_code)` + `ORDER BY` preference: exact → alias → uniprot match
- [x] T059 M6: Rename `specs/.../indication_epidemiology.sql` is a docs note; rename actual file `ind/silver/indication_epidemiology.sql` → `ind/silver/epidemiology.sql` to match MODEL name `ind_silver.epidemiology`
- [x] T060 M7: Fix `mol_silver.patent_exclusivities.sql` — remove `processed_to_silver = FALSE` filters in both CTEs (FULL models rebuild entirely; this filter empties the table after first run)

### Low

- [x] T061 L2: Fix `main.py` — add `_prom_start_http_server(8000)` call in `main()` before `init_connection_pool()` so CronJob pods expose `/metrics` for Prometheus scraping
- [x] T062 L3: Fix `main.py` — add `'batch_size'` to `_INTERNAL_KWARGS` set (was leaking to `fetcher.fetch()` causing `TypeError: unexpected keyword argument`)
- [x] T063 L5: Fix `main.py` line 1149 — `datetime.now()` → `datetime.now(timezone.utc)` in `log_to_meta()`

---

## Phase 8: Audit #5 (#176) — Remaining Gaps

- [x] T064 S1: Fix `hcs_silver.cms_drug_market.sql` — Part B CTE now groups by `(hcpcs_desc, _source_year)` only; `hcpcs_cd`/`mftr_name` aggregated via `STRING_AGG` (carried from H7, final fix here)
- [x] T065 S2: Delete `mol_silver.healthcare_facilities.sql` — duplicate of `hcs_silver.healthcare_facilities` with fewer columns; no downstream consumers; HCS version is canonical
- [x] T066 S9: Add `mol_raw.websearch` to `mol_bronze/_external_sources.yaml` — prevents SQLMesh strict-mode validation failure for `mol_bronze.websearch_results → mol_silver.web_content` chain
- [x] T067 Add `DISTINCT ON` + `ORDER BY` to 5 silver models with fan-out from multi-year bronze joins:
  - `hcs_silver.cms_formulary` — alias join fan-out; `DISTINCT ON (formulary_id, rxcui)`
  - `hcs_silver.cms_pecos` — `cms_nppes` grain `(npi, _source_year)`; `DISTINCT ON (enrollment_id)`, most recent year
  - `hcs_silver.cms_dmepos` — same `cms_nppes` fan-out; `DISTINCT ON (npi)`, most recent year
  - `hcs_silver.cms_chow` — `cms_hospital_general_info` grain `(facility_id, _source_year)`; `DISTINCT ON (ccn, effective_date)`, most recent year
  - `hcs_silver.cms_hospital_affiliation` — both `cms_nppes` + `cms_hospital_general_info` fan-out; `DISTINCT ON (npi, cert_number)`, most recent year for each

---

## Phase 9: Operational Improvements (#175 L1, L4)

- [x] T068 L1/S7: Add `retry_with_backoff(max_attempts=3, initial_delay=30, max_delay=120)` wrapper around `run_ingestion()` in `initial_backfill._fetch_one()` — catches transient failures above the HTTP-request level
- [x] T069 L4/S8: Add `mark_job_success(f'backfill_fetch_{source}')` on `status in ('success', 'partial')` in `initial_backfill._fetch_one()` — enables per-source Prometheus staleness alerting

---

## Phase 10: Dead-End Bronze → Silver Promotion

All 7 bronze sources that had no silver consumer. `cms_ddinter` excluded (retired source).

- [x] T070 Create `hcs_silver.cms_cost_reports_puf_lines` — staffing/labor cost data; links `provider_id` → `cms_hospital_general_info` (DISTINCT ON, most recent year)
- [x] T071 Create `hcs_silver.cms_hospital_info` — typed pass-through; no upstream join (this IS facility reference data)
- [x] T072 Create `hcs_silver.cms_physician_puf_services` — NPI-by-HCPCS utilization; NPI → `cms_nppes` (DISTINCT ON); `hcpcs_code` → `hcpcs_molecule_bridge` (LATERAL, drug-flagged rows only)
- [x] T073 Create `hcs_silver.cms_post_acute` — SNF/HHA/IRF/LTCH metrics; `ccn` → `cms_hospital_general_info` (DISTINCT ON, most recent year)
- [x] T074 Create `hcs_silver.cms_stabilis` — IV drug compatibility; `drug_a` + `drug_b` each → `molecule_aliases` (LATERAL LIMIT 1)
- [x] T075 Create `hcs_silver.cms_usp` — USP drug classification; `rxcui` → `identifier_mappings` (LATERAL LIMIT 1); fallback `branded_name` → `molecule_aliases`
- [x] T076 Create `mol_silver.ema_regulatory_docs` — EMA regulatory document records; `active_substance` → `molecules` canonical exact, then alias normalized + first-token (LATERAL LIMIT 1)

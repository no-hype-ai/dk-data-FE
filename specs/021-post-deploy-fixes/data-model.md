# Data Model: Post-Deployment Fixes, SQL Audit & Silver Gap Closure

**Branch**: `021-post-deploy-fixes`

---

## Schema Changes Overview

This feature introduces 7 new silver models, removes 1 duplicate silver model, renames 1 silver model file, and fixes SQL bugs in 16 existing models. No new raw or bronze schemas. No new migrations.

---

## New Silver Models

### `hcs_silver.cms_cost_reports_puf_lines`
**File**: `src/dk_data/sqlmesh/models/hcs/silver/cms_cost_reports_puf_lines.sql`
**Kind**: FULL | **Cron**: @monthly | **Grain**: `(provider_id, line_item_code, _source_year)`
**Source**: `hcs_bronze.cms_cost_reports_puf_lines`
**Linkage**: `provider_id` → `hcs_bronze.cms_hospital_general_info` (DISTINCT ON, most recent year)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | gen_random_uuid() |
| `provider_id` | TEXT | Healthcare facility identifier |
| `line_item_code` | TEXT | Staffing classification code |
| `line_item_description` | TEXT | Human-readable category |
| `reported_hours_fte` | NUMERIC | FTE hours reported |
| `total_salaries` | NUMERIC | Aggregate salary costs |
| `facility_type` | TEXT | Facility type classification |
| `_source_year` | INTEGER | Fiscal year |
| `facility_name` | TEXT | From cms_hospital_general_info |
| `facility_city` | TEXT | From cms_hospital_general_info |
| `facility_state` | TEXT | From cms_hospital_general_info |
| `hospital_type` | TEXT | From cms_hospital_general_info |

---

### `hcs_silver.cms_hospital_info`
**File**: `src/dk_data/sqlmesh/models/hcs/silver/cms_hospital_info.sql`
**Kind**: FULL | **Cron**: @daily | **Grain**: `provider_id`
**Source**: `hcs_bronze.cms_hospital_info`
**Linkage**: Pass-through only — this IS facility reference data

| Column | Type | Notes |
|--------|------|-------|
| `provider_id` | TEXT | Hospital facility identifier |
| `hospital_name` | TEXT | — |
| `address` | TEXT | — |
| `city` | TEXT | — |
| `state` | TEXT | — |
| `zip_code` | TEXT | — |
| `county_name` | TEXT | — |
| `phone_number` | TEXT | — |
| `hospital_type` | TEXT | — |
| `ownership` | TEXT | — |
| `emergency_services` | BOOLEAN | — |
| `rating` | INTEGER | Overall quality rating |

---

### `hcs_silver.cms_physician_puf_services`
**File**: `src/dk_data/sqlmesh/models/hcs/silver/cms_physician_puf_services.sql`
**Kind**: FULL | **Cron**: @monthly | **Grain**: `(npi, hcpcs_code, place_of_service, _source_year)`
**Source**: `hcs_bronze.cms_physician_puf_services`
**Linkage**:
- NPI → `hcs_bronze.cms_nppes` (DISTINCT ON, most recent year)
- `hcpcs_code` → `mol_silver.hcpcs_molecule_bridge` (LATERAL, confidence-ranked, drug-flagged rows only)

| Column | Type | Notes |
|--------|------|-------|
| `npi` | TEXT | National Provider Identifier |
| `hcpcs_code` | TEXT | Procedure code |
| `hcpcs_description` | TEXT | — |
| `hcpcs_drug_ind` | TEXT | 'Y' = drug HCPCS code |
| `place_of_service` | TEXT | Office/hospital/facility |
| `line_srvc_cnt` | NUMERIC | Services count |
| `bene_unique_cnt` | INTEGER | Unique beneficiaries |
| `average_medicare_payment_amt` | NUMERIC | — |
| `provider_name` | TEXT | From cms_nppes |
| `provider_specialty` | TEXT | From cms_nppes |
| `provider_state` | TEXT | From cms_nppes |
| `molecule_id` | UUID | Via hcpcs_molecule_bridge (drug rows only) |
| `molecule_link_confidence` | NUMERIC | Bridge confidence score |

---

### `hcs_silver.cms_post_acute`
**File**: `src/dk_data/sqlmesh/models/hcs/silver/cms_post_acute.sql`
**Kind**: FULL | **Cron**: @monthly | **Grain**: `(ccn, year)`
**Source**: `hcs_bronze.cms_post_acute`
**Linkage**: `ccn` → `hcs_bronze.cms_hospital_general_info` (DISTINCT ON, most recent year)

| Column | Type | Notes |
|--------|------|-------|
| `ccn` | TEXT | CMS Certification Number |
| `provider_name` | TEXT | — |
| `provider_type` | TEXT | SNF/HHA/IRF/LTCH |
| `total_episodes` | INTEGER | Care episodes |
| `avg_episode_payment` | NUMERIC | — |
| `readmission_rate` | NUMERIC | Quality metric |
| `year` | INTEGER | — |
| `facility_city` | TEXT | From cms_hospital_general_info |
| `facility_state` | TEXT | From cms_hospital_general_info |

---

### `hcs_silver.cms_stabilis`
**File**: `src/dk_data/sqlmesh/models/hcs/silver/cms_stabilis.sql`
**Kind**: FULL | **Cron**: @monthly | **Grain**: `(drug_a, drug_b)`
**Source**: `hcs_bronze.cms_stabilis`
**Linkage**: `drug_a` + `drug_b` each → `mol_silver.molecule_aliases` (LATERAL LIMIT 1, normalized name)

| Column | Type | Notes |
|--------|------|-------|
| `drug_a` | TEXT | First drug in pair |
| `drug_b` | TEXT | Second drug in pair |
| `compatibility` | TEXT | compatible/incompatible/requires monitoring |
| `solvent` | TEXT | IV diluent |
| `concentration` | TEXT | Test concentration |
| `reference` | TEXT | Clinical citation |
| `molecule_id_a` | UUID | Via molecule_aliases on drug_a |
| `molecule_id_b` | UUID | Via molecule_aliases on drug_b |

---

### `hcs_silver.cms_usp`
**File**: `src/dk_data/sqlmesh/models/hcs/silver/cms_usp.sql`
**Kind**: FULL | **Cron**: @monthly | **Grain**: `rxcui`
**Source**: `hcs_bronze.cms_usp`
**Linkage**:
- Tier 1: `rxcui` → `mol_silver.identifier_mappings` (identifier_type='rxcui', LATERAL LIMIT 1)
- Tier 2: `branded_name` → `mol_silver.molecule_aliases` (normalized, LATERAL LIMIT 1)

| Column | Type | Notes |
|--------|------|-------|
| `rxcui` | TEXT | RxNorm Concept Unique Identifier |
| `tty` | TEXT | Term type classification |
| `branded_name` | TEXT | Commercial drug name |
| `usp_category` | TEXT | USP therapeutic category |
| `usp_class` | TEXT | USP drug class |
| `molecule_id` | UUID | Via rxcui→identifier_mappings or branded_name→aliases |

---

### `mol_silver.ema_regulatory_docs`
**File**: `src/dk_data/sqlmesh/models/molecules/silver/ema_regulatory_docs.sql`
**Kind**: FULL | **Cron**: @weekly | **Grain**: `document_id`
**Source**: `mol_bronze.ema_regulatory`
**Linkage**:
- Tier 1: `active_substance` → `mol_silver.molecules` (canonical_name exact)
- Tier 2: `active_substance` → `mol_silver.molecule_aliases` (full normalized + first-token, LATERAL LIMIT 1)

| Column | Type | Notes |
|--------|------|-------|
| `document_id` | TEXT | EMA document identifier |
| `document_type` | TEXT | EPAR/PAR/etc. |
| `product_name` | TEXT | Commercial name |
| `active_substance` | TEXT | INN / active ingredient |
| `therapeutic_area` | TEXT | — |
| `decision_date` | DATE | — |
| `decision_type` | TEXT | approval/conditional/rejection |
| `document_url` | TEXT | EMA document link |
| `molecule_id` | UUID | Via active_substance linkage |
| `link_strategy` | TEXT | canonical_exact / alias_match / unlinked |

---

## Removed Models

| Model | File | Reason |
|-------|------|--------|
| `mol_silver.healthcare_facilities` | `molecules/silver/healthcare_facilities.sql` | Duplicate of `hcs_silver.healthcare_facilities` (104 vs 146 lines; HCS version has more columns, cron, processed_to_silver). No downstream consumers of mol_silver version. |

---

## Renamed Files

| Before | After | Reason |
|--------|-------|--------|
| `ind/silver/indication_epidemiology.sql` | `ind/silver/epidemiology.sql` | MODEL name is `ind_silver.epidemiology`; file name must match for developer clarity |

---

## External Source Declarations Added

**File**: `src/dk_data/sqlmesh/models/molecules/bronze/_external_sources.yaml`

| Source | Description |
|--------|-------------|
| `mol_raw.websearch` | Web search results populated by agent side-channel; consumed by `mol_bronze.websearch_results` → `mol_silver.web_content` |

---

## Modified Silver Models (SQL Bug Fixes)

| Model | File | Fix Applied |
|-------|------|-------------|
| `mol_silver.orange_book` | `molecules/silver/orange_book.sql` | `m.inn_name`/`m.preferred_name` → `m.canonical_name` |
| `mol_silver.healthcare_facilities` | `molecules/silver/healthcare_facilities.sql` | Wrong bronze names corrected (see hcs version) |
| `mol_silver.protein_structures` | `molecules/silver/protein_structures.sql` | `identifier_type = 'pdb_ligand'` → `'pubchem_cid'` |
| `mol_silver.proteins` | `molecules/silver/proteins.sql` | `identifier_type = 'uniprot'` → `'uniprot_id'` |
| `mol_silver.ema_regulatory` | `molecules/silver/ema_regulatory.sql` | LATERAL LIMIT 1 alias join replaces open JOIN |
| `mol_silver.imgt` | `molecules/silver/imgt.sql` | `DISTINCT ON (pdb_code)` + ORDER BY preference added |
| `mol_silver.cochrane_reviews` | `molecules/silver/cochrane_reviews.sql` | `DISTINCT ON (review_id)` + grain declaration |
| `mol_silver.nice_hta` | `molecules/silver/nice_hta.sql` | `DISTINCT ON (guidance_id)` + alias join guard |
| `mol_silver.ttd` | `molecules/silver/ttd.sql` | `DISTINCT ON (ttd_id)` + alias join guards |
| `mol_silver.drug_spending` | `molecules/silver/drug_spending.sql` | Part D brnd_name out of GROUP BY; STRING_AGG |
| `mol_silver.patent_exclusivities` | `molecules/silver/patent_exclusivities.sql` | `processed_to_silver = FALSE` filters removed |
| `mol_silver.molecule_targets` | `molecules/silver/molecule_targets.sql` | DrugBank target join: strpos → exact match |
| `hcs_silver.cms_ndc` | `hcs/silver/cms_ndc.sql` | `DISTINCT ON (product_ndc)` + alias join guard |
| `hcs_silver.cms_drug_market` | `hcs/silver/cms_drug_market.sql` | Part B CTE grouped by `(generic_name, _source_year)` only; hcpcs_cd/mftr_name via STRING_AGG |
| `hcs_silver.cms_formulary` | `hcs/silver/cms_formulary.sql` | `DISTINCT ON (formulary_id, rxcui)` |
| `hcs_silver.cms_pecos` | `hcs/silver/cms_pecos.sql` | `DISTINCT ON (enrollment_id)`, most recent nppes year |
| `hcs_silver.cms_dmepos` | `hcs/silver/cms_dmepos.sql` | `DISTINCT ON (npi)`, most recent nppes year |
| `hcs_silver.cms_chow` | `hcs/silver/cms_chow.sql` | `DISTINCT ON (ccn, effective_date)`, most recent hgi year |
| `hcs_silver.cms_hospital_affiliation` | `hcs/silver/cms_hospital_affiliation.sql` | `DISTINCT ON (npi, cert_number)`, most recent year for both joins |

---

## Modified Gold Models (SQL Bug Fixes)

| Model | File | Fix Applied |
|-------|------|-------------|
| `mol_gold.financial_summary` | `molecules/gold/financial_summary.sql` | Molecule linkage via `clinical_trials.lead_sponsor` instead of `company_name = canonical_name` |
| `mol_gold.company_pipeline` | `molecules/gold/company_pipeline.sql` | JSON key `interventionType` → `type` |

---

## Configuration Changes

| File | Change |
|------|--------|
| `src/dk_data/ingestion/main.py` | `_prom_start_http_server(8000)` added; `'batch_size'` added to `_INTERNAL_KWARGS`; `datetime.now(timezone.utc)` in `log_to_meta()` |
| `src/dk_data/ingestion/initial_backfill.py` | `retry_with_backoff` import + decorator on `run_ingestion`; `mark_job_success` per source on success |
| `src/dk_data/ingestion/fetchers/who_icd.py` | Full rewrite: dynamic discovery, ICD-10 recursive walker, corrected API URL |
| `src/dk_data/sqlmesh/models/molecules/bronze/who_icd.sql` | `title->>'@value'` extraction; `coding_hint` column added |
| `src/dk_data/sqlmesh/models/molecules/silver/icd_codes.sql` | Correct parent_code derivation; `coding_hint` passthrough |

---

## Impacted Tables (Read-Only Reference — No Schema Change)

| Table | Schema | Change |
|-------|--------|--------|
| `hcs_raw.cms_ddinter` | hcs_raw | No change — existing data preserved; fetcher removed |
| `hcs_bronze.cms_ddinter` | hcs_bronze | No change — model retained with retirement comment |
| `mol_bronze.drugbank_data` | mol_bronze | No change — confirmed as DDI replacement source |
| `meta.data_sources` | meta | DDInter entries stop accumulating after CronJob pruned |
| `meta.refresh_log` | meta | DDInter entries stop accumulating after CronJob pruned |

## Kubernetes Secret: `dk-data-secrets`

| Key | Before | After |
|-----|--------|-------|
| `EPO_CONSUMER_KEY` | `CHANGEME_obtain_from_developers_epo_org` | Real OAuth2 consumer key |
| `EPO_CONSUMER_SECRET` | `CHANGEME_obtain_from_developers_epo_org` | Real OAuth2 consumer secret |

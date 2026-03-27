# Data Model: CMS PUF & Platform Data Reconciliation

**Phase**: 1 — Design
**Feature**: `019-cms-puf-platform-reconciliation`
**Date**: 2026-03-27

---

## Schema Overview

Eight schema namespaces. Two domain prefixes (`mol_` = molecule/regulatory/clinical, `hcs_` = healthcare/CMS). Four layers per domain.

| Schema | Layer | Contents |
|---|---|---|
| `mol_raw` | Raw | JSONB archive of API responses (EuropePMC, EMA, NIH Reporter, PubChem) |
| `hcs_raw` | Raw | Direct-normalized CMS PUF file rows (typed columns, `_source_hash`) |
| `mol_bronze` | Bronze | Typed extraction from `mol_raw` JSONB |
| `hcs_bronze` | Bronze | Typed pass-through from `hcs_raw` with light normalisation |
| `mol_silver` | Silver | Normalized, entity-linked molecule domain records |
| `hcs_silver` | Silver | Normalized CMS records (NDC grain, USP classification) |
| `mol_gold` | Gold | Aggregated, decision-ready molecule views |
| `hcs_gold` | Gold | Aggregated CMS market profiles |

---

## Raw Layer Entities

### mol_raw (JSONB archive pattern)

All API-based sources. One row per API response document.

**`mol_raw.europepmc_raw`**
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `pmid` | VARCHAR(20) | PubMed ID — deduplication key |
| `source` | VARCHAR(20) | 'europepmc' |
| `response_body` | JSONB | Full API response document |
| `processed_to_bronze` | BOOLEAN | DEFAULT FALSE; set TRUE after bronze extraction |
| `_loaded_at` | TIMESTAMP | DEFAULT NOW() |

**`mol_raw.ema_regulatory_raw`**
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `product_number` | VARCHAR(50) | EMA product number — deduplication key |
| `source` | VARCHAR(20) | 'ema_regulatory' |
| `response_body` | JSONB | Full EPAR/CHMP document |
| `processed_to_bronze` | BOOLEAN | DEFAULT FALSE |
| `_loaded_at` | TIMESTAMP | DEFAULT NOW() |

**`mol_raw.nih_reporter_raw`**
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `project_number` | VARCHAR(50) | NIH project number |
| `source` | VARCHAR(20) | 'nih_reporter' |
| `response_body` | JSONB | Full grant record |
| `processed_to_bronze` | BOOLEAN | DEFAULT FALSE |
| `_loaded_at` | TIMESTAMP | DEFAULT NOW() |

---

### hcs_raw (Direct-normalized pattern)

All CMS PUF file-based sources. Columns mirror the CSV schema exactly. Only universal columns shown; source-specific columns documented per-table.

**Universal columns on every `hcs_raw.*` table**:
| Column | Type | Notes |
|---|---|---|
| `_source_hash` | VARCHAR(64) | MD5 of source file — skip-if-present dedup key |
| `_loaded_at` | TIMESTAMP | DEFAULT NOW() |
| `_source_year` | INTEGER | Fiscal/calendar year of the file |

**`hcs_raw.cms_part_d_spending`** (Part D Drug Spending by Drug)
| Column | Type |
|---|---|
| `generic_name` | VARCHAR(200) |
| `brand_name` | VARCHAR(200) |
| `manufacturer` | VARCHAR(200) |
| `tot_mftr` | INTEGER |
| `tot_spndng` | NUMERIC(15,2) |
| `tot_dsg_unts` | NUMERIC(15,2) |
| `tot_clms` | INTEGER |
| `tot_benes` | INTEGER |
| `ge65_spndng` | NUMERIC(15,2) |
| `ge65_tot_clms` | INTEGER |
| `ge65_tot_benes` | INTEGER |
| `_source_hash` | VARCHAR(64) |
| `_loaded_at` | TIMESTAMP |
| `_source_year` | INTEGER |

**`hcs_raw.cms_part_b_spending`** (Part B Drug Spending by Drug/HCPCS)
| Column | Type |
|---|---|
| `hcpcs_code` | VARCHAR(10) |
| `hcpcs_description` | VARCHAR(300) |
| `drug_indicator` | VARCHAR(1) |
| `tot_allowed_charges` | NUMERIC(15,2) |
| `tot_services` | INTEGER |
| `tot_suppliers` | INTEGER |
| `tot_beneficiaries` | INTEGER |
| `avg_allowed_charge` | NUMERIC(10,2) |
| `avg_submitted_charge` | NUMERIC(10,2) |
| `_source_hash`, `_loaded_at`, `_source_year` | — | Universal |

**`hcs_raw.cms_open_payments`** (Open Payments — physician/industry payments)
| Column | Type |
|---|---|
| `record_id` | VARCHAR(50) PK |
| `physician_id` | VARCHAR(20) |
| `physician_first_name` | VARCHAR(100) |
| `physician_last_name` | VARCHAR(100) |
| `physician_specialty` | VARCHAR(200) |
| `recipient_state` | VARCHAR(2) |
| `applicable_manufacturer` | VARCHAR(200) |
| `product_category` | VARCHAR(100) |
| `product_name` | VARCHAR(200) |
| `total_amount_of_payment` | NUMERIC(12,2) |
| `date_of_payment` | DATE |
| `nature_of_payment` | VARCHAR(100) |
| `_source_hash`, `_loaded_at`, `_source_year` | — | Universal |

**`hcs_raw.cms_nppes`** (NPI registry)
| Column | Type |
|---|---|
| `npi` | VARCHAR(10) |
| `entity_type_code` | VARCHAR(1) |
| `provider_last_name` | VARCHAR(100) |
| `provider_first_name` | VARCHAR(100) |
| `provider_organization_name` | VARCHAR(200) |
| `provider_primary_taxonomy_code` | VARCHAR(10) |
| `provider_business_mailing_address_state` | VARCHAR(2) |
| `provider_business_mailing_address_postal_code` | VARCHAR(10) |
| `_source_hash`, `_loaded_at`, `_source_year` | — | Universal |

**`hcs_raw.cms_inpatient_puf`** (Medicare Inpatient PUF — DRG level)
| Column | Type |
|---|---|
| `drg_definition` | VARCHAR(200) |
| `provider_id` | VARCHAR(10) |
| `provider_name` | VARCHAR(200) |
| `provider_state` | VARCHAR(2) |
| `hospital_referral_region` | VARCHAR(100) |
| `total_discharges` | INTEGER |
| `average_covered_charges` | NUMERIC(12,2) |
| `average_total_payments` | NUMERIC(12,2) |
| `average_medicare_payments` | NUMERIC(12,2) |
| `_source_hash`, `_loaded_at`, `_source_year` | — | Universal |

**`hcs_raw.cms_physician_puf`** (Medicare Physician & Other Supplier PUF)
| Column | Type |
|---|---|
| `npi` | VARCHAR(10) |
| `nppes_provider_last_org` | VARCHAR(100) |
| `nppes_provider_first` | VARCHAR(100) |
| `nppes_credentials` | VARCHAR(50) |
| `nppes_provider_gender` | VARCHAR(1) |
| `nppes_entity_code` | VARCHAR(1) |
| `nppes_provider_state` | VARCHAR(2) |
| `provider_type` | VARCHAR(100) |
| `medicare_participation_indicator` | VARCHAR(1) |
| `place_of_service` | VARCHAR(1) |
| `hcpcs_code` | VARCHAR(10) |
| `hcpcs_description` | VARCHAR(300) |
| `hcpcs_drug_indicator` | VARCHAR(1) |
| `line_srvc_cnt` | NUMERIC(12,2) |
| `bene_unique_cnt` | INTEGER |
| `bene_day_srvc_cnt` | INTEGER |
| `average_medicare_allowed_amt` | NUMERIC(10,2) |
| `average_submitted_chrg_amt` | NUMERIC(10,2) |
| `average_medicare_payment_amt` | NUMERIC(10,2) |
| `_source_hash`, `_loaded_at`, `_source_year` | — | Universal |

**`hcs_raw.cms_hospital_general_info`**
| Column | Type |
|---|---|
| `facility_id` | VARCHAR(10) |
| `facility_name` | VARCHAR(200) |
| `address` | VARCHAR(200) |
| `city` | VARCHAR(100) |
| `state` | VARCHAR(2) |
| `zip_code` | VARCHAR(10) |
| `county_name` | VARCHAR(100) |
| `phone_number` | VARCHAR(15) |
| `hospital_type` | VARCHAR(100) |
| `hospital_ownership` | VARCHAR(100) |
| `emergency_services` | VARCHAR(5) |
| `hospital_overall_rating` | VARCHAR(5) |
| `_source_hash`, `_loaded_at`, `_source_year` | — | Universal |

---

## Bronze Layer Entities

### mol_bronze (JSONB extraction)

**`mol_bronze.europepmc`**
| Column | Type | Source field |
|---|---|---|
| `pmid` | VARCHAR(20) | `pmid` |
| `title` | TEXT | `title` |
| `abstract_text` | TEXT | `abstractText` |
| `journal_title` | VARCHAR(300) | `journalInfo->>'journal'` |
| `publication_date` | DATE | `firstPublicationDate` |
| `author_list` | JSONB | `authorList->'author'` (kept as array) |
| `mesh_headings` | JSONB | `meshHeadingList` |
| `doi` | VARCHAR(100) | `doi` |
| `_source_pmid` | VARCHAR(20) | dedup key |
| `_processed_at` | TIMESTAMP | extraction timestamp |

**`mol_bronze.ema_regulatory`**
| Column | Type | Source field (EMA JSON uses spaces in keys) |
|---|---|---|
| `product_number` | VARCHAR(50) | `'Product number'` |
| `medicine_name` | VARCHAR(200) | `'Medicine name'` |
| `active_substance` | VARCHAR(300) | `'Active substance'` |
| `inn` | VARCHAR(300) | `'INN - international non-proprietary name'` |
| `authorisation_status` | VARCHAR(50) | `'Authorisation status'` |
| `atc_code` | VARCHAR(20) | `'ATC code'` |
| `indication` | TEXT | `'Therapeutic indication'` |
| `authorisation_date` | DATE | `'Date of authorisation'` |
| `orphan_medicine` | BOOLEAN | `'Orphan medicine'` |
| `_processed_at` | TIMESTAMP | |

**`mol_bronze.nih_reporter`**
| Column | Type | Source field |
|---|---|---|
| `project_number` | VARCHAR(50) | `project_num` |
| `project_title` | TEXT | `project_title` |
| `fiscal_year` | INTEGER | `fiscal_year` |
| `pi_names` | JSONB | `principal_investigators` |
| `organization_name` | VARCHAR(200) | `organization.org_name` |
| `total_cost` | NUMERIC(15,2) | `award_amount` |
| `abstract_text` | TEXT | `abstract_text` |
| `terms` | TEXT | `terms` |
| `start_date` | DATE | `project_start_date` |
| `end_date` | DATE | `project_end_date` |
| `_processed_at` | TIMESTAMP | |

### hcs_bronze (typed pass-through)

Bronze for CMS sources mirrors raw with light normalisation (trim whitespace, standardise nulls, normalise year). Same columns as raw minus `_source_hash`, adding `_bronze_loaded_at`.

---

## Silver Layer Entities

### mol_silver (entity-linked)

**`mol_silver.ema_regulatory`** — EMA decisions linked to platform molecules
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `molecule_id` | UUID FK | `mol_silver.molecules.molecule_id`; NULL if unlinked |
| `product_number` | VARCHAR(50) | Unique EMA identifier |
| `medicine_name` | VARCHAR(200) | |
| `active_substance` | VARCHAR(300) | |
| `authorisation_status` | VARCHAR(50) | 'authorised', 'refused', 'withdrawn' |
| `indication` | TEXT | |
| `authorisation_date` | DATE | |
| `orphan_medicine` | BOOLEAN | |
| `atc_code` | VARCHAR(20) | |
| `link_strategy` | VARCHAR(50) | 'exact_name', 'inn_match', 'unlinked' |
| `_loaded_at` | TIMESTAMP | |

**`mol_silver.drug_spending`** — Part D + Part B spending unified
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `molecule_id` | UUID FK | nullable |
| `generic_name` | VARCHAR(200) | |
| `brand_name` | VARCHAR(200) | |
| `program` | VARCHAR(10) | 'part_d', 'part_b' |
| `year` | INTEGER | |
| `total_spending` | NUMERIC(15,2) | |
| `total_claims` | INTEGER | |
| `total_beneficiaries` | INTEGER | |
| `avg_spending_per_claim` | NUMERIC(10,2) | spending / claims |
| `link_strategy` | VARCHAR(50) | |
| `_loaded_at` | TIMESTAMP | |

**`mol_silver.physician_payments`** — Open Payments linked to molecules
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `molecule_id` | UUID FK | nullable |
| `source_record_id` | VARCHAR(50) | from `hcs_raw.cms_open_payments.record_id` |
| `physician_npi` | VARCHAR(10) | |
| `manufacturer` | VARCHAR(200) | |
| `product_name` | VARCHAR(200) | |
| `payment_amount` | NUMERIC(12,2) | |
| `payment_date` | DATE | |
| `nature_of_payment` | VARCHAR(100) | |
| `_loaded_at` | TIMESTAMP | |

**`mol_silver.research_grants`** — NIH grants linked to molecules
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `molecule_id` | UUID FK | nullable |
| `project_number` | VARCHAR(50) | |
| `project_title` | TEXT | |
| `fiscal_year` | INTEGER | |
| `total_cost` | NUMERIC(15,2) | |
| `organization_name` | VARCHAR(200) | |
| `_loaded_at` | TIMESTAMP | |

**`mol_silver.publication_evidence`** — LLM-extracted clinical endpoints
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `molecule_id` | UUID FK | nullable |
| `trial_nct_id` | VARCHAR(20) | nullable |
| `endpoint_name` | VARCHAR(200) | NOT NULL |
| `endpoint_type` | VARCHAR(50) | CHECK IN ('primary','secondary','exploratory') |
| `hazard_ratio` | NUMERIC(8,4) | |
| `p_value` | NUMERIC(10,8) | |
| `response_rate` | NUMERIC(5,2) | |
| `median_survival_months` | NUMERIC(6,1) | |
| `sample_size` | INTEGER | |
| `confidence_score` | NUMERIC(3,2) | NOT NULL; CHECK 0.0–1.0 |
| `doi` | VARCHAR(100) | |
| `pmid` | VARCHAR(20) | |
| `extraction_metadata` | JSONB | LLM prompt/response metadata |
| `content_hash` | VARCHAR(64) | NOT NULL UNIQUE — INCREMENTAL dedup key |
| `needs_review` | BOOLEAN | NOT NULL DEFAULT FALSE |
| `_loaded_at` | TIMESTAMP | NOT NULL DEFAULT NOW() |

**`mol_silver.agent_quarantine`** — Agent results below confidence threshold
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `agent_name` | VARCHAR(100) | which agent produced it |
| `source_record_id` | UUID | FK to source entity |
| `confidence_score` | NUMERIC(3,2) | < 0.5 by definition |
| `raw_output` | JSONB | full agent response |
| `created_at` | TIMESTAMP | |
| `reviewed_at` | TIMESTAMP | nullable |
| `resolution` | VARCHAR(50) | nullable: 'accepted', 'rejected' |

### hcs_silver

**`hcs_silver.cms_drug_market`** — NDC-grain drug market profile
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `ndc` | VARCHAR(11) | National Drug Code — grain key |
| `generic_name` | VARCHAR(200) | |
| `brand_name` | VARCHAR(200) | |
| `manufacturer` | VARCHAR(200) | |
| `part_d_spending` | NUMERIC(15,2) | |
| `part_b_spending` | NUMERIC(15,2) | |
| `total_spending` | NUMERIC(15,2) | |
| `total_beneficiaries` | INTEGER | |
| `usp_category` | VARCHAR(100) | USP classification join |
| `rbcs_category` | VARCHAR(100) | CMS RBCS classification |
| `year` | INTEGER | |
| `_loaded_at` | TIMESTAMP | |

---

## Gold Layer Entities

### mol_gold

**`mol_gold.trial_outcomes`** — Registry + publication evidence unified
| Column | Type | Notes |
|---|---|---|
| `id` | UUID | `gen_random_uuid()` |
| `molecule_id` | UUID | |
| `trial_nct_id` | VARCHAR(20) | |
| `evidence_source` | VARCHAR(30) | 'clinicaltrials_gov', 'publication' |
| `endpoint_name` | VARCHAR(200) | |
| `hazard_ratio` | NUMERIC(8,4) | |
| `p_value` | NUMERIC(10,8) | |
| `response_rate` | NUMERIC(5,2) | |
| `sample_size` | INTEGER | |
| `confidence_score` | NUMERIC(3,2) | 1.0 for registry; ≥0.40 for publication |
| `evidence_date` | DATE | |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Grain**: `(molecule_id, trial_nct_id, endpoint_name, evidence_source)`
**Source rules**: ClinicalTrials.gov rows included always; publication evidence included when `confidence_score >= 0.40 AND needs_review = FALSE`
**Xenon removal**: `publication_outcomes` CTE reads from `mol_silver.publication_evidence` — not `xenon.publication_evidence`

**`mol_gold.market_summary`** — Per-molecule 10-source aggregate
| Column | Type | Notes |
|---|---|---|
| `molecule_id` | UUID PK | |
| `canonical_name` | VARCHAR(200) | |
| `development_status` | VARCHAR(50) | |
| `max_phase` | INTEGER | |
| `total_part_d_spending` | NUMERIC(15,2) | NULL if no data |
| `total_part_b_spending` | NUMERIC(15,2) | NULL if no data |
| `ema_authorisation_status` | VARCHAR(50) | NULL if no data |
| `ema_authorisation_date` | DATE | NULL if no data |
| `cochrane_review_count` | INTEGER | 0 if no data |
| `europepmc_publication_count` | INTEGER | 0 if no data |
| `nih_grant_count` | INTEGER | 0 if no data |
| `nih_total_funding` | NUMERIC(15,2) | NULL if no data |
| `trial_count` | INTEGER | from trial_outcomes |
| `publication_evidence_count` | INTEGER | from mol_silver.publication_evidence |
| `last_updated` | TIMESTAMP | |

### hcs_gold

**`hcs_gold.cms_drug_market_profile`** — NDC market profile with rankings
| Column | Type | Notes |
|---|---|---|
| `ndc` | VARCHAR(11) PK | |
| `generic_name` | VARCHAR(200) | |
| `brand_name` | VARCHAR(200) | |
| `manufacturer` | VARCHAR(200) | |
| `total_spending` | NUMERIC(15,2) | |
| `market_share_pct` | NUMERIC(5,2) | % of total CMS spending for generic_name group |
| `beneficiary_count` | INTEGER | |
| `usp_category` | VARCHAR(100) | |
| `rbcs_category` | VARCHAR(100) | |
| `spending_rank_in_category` | INTEGER | RANK() OVER category, NULLS LAST |
| `year` | INTEGER | |

---

## State Tracking Entities (existing on main)

**`meta.data_sources`**
| Column | Type |
|---|---|
| `source_id` | SERIAL PK |
| `source_name` | VARCHAR(100) UNIQUE |
| `source_type` | VARCHAR(50) |
| `description` | TEXT |
| `default_days_back` | INTEGER |
| `last_successful_refresh` | TIMESTAMP |
| `last_refresh_status` | VARCHAR(20) |
| `last_refresh_attempt` | TIMESTAMP |

**`meta.refresh_log`**
| Column | Type |
|---|---|
| `log_id` | SERIAL PK |
| `source_id` | INTEGER FK |
| `refresh_started_at` | TIMESTAMP |
| `refresh_completed_at` | TIMESTAMP |
| `status` | VARCHAR(20) |
| `records_fetched` | INTEGER |
| `records_inserted` | INTEGER |
| `records_updated` | INTEGER |
| `error_message` | JSONB |

---

## Entity Relationships

```
mol_silver.molecules (1) ──< (0..N) mol_silver.ema_regulatory
mol_silver.molecules (1) ──< (0..N) mol_silver.drug_spending
mol_silver.molecules (1) ──< (0..N) mol_silver.physician_payments
mol_silver.molecules (1) ──< (0..N) mol_silver.research_grants
mol_silver.molecules (1) ──< (0..N) mol_silver.publication_evidence
mol_silver.publication_evidence ──> mol_gold.trial_outcomes (via UNION)
mol_silver.clinical_trials ──> mol_gold.trial_outcomes (via UNION)
mol_silver.drug_spending ──> mol_gold.market_summary
mol_silver.ema_regulatory ──> mol_gold.market_summary
hcs_silver.cms_drug_market ──> hcs_gold.cms_drug_market_profile
meta.data_sources (1) ──< (0..N) meta.refresh_log
```

---

## Identity and Uniqueness Rules

- `mol_silver.molecules.molecule_id` is the cross-source join key (UUID, existing)
- `mol_silver.publication_evidence.content_hash` is the INCREMENTAL_BY_UNIQUE_KEY dedup key
- `hcs_raw.*._source_hash` is the file-level dedup key (MD5 of CSV file)
- `hcs_silver.cms_drug_market.ndc` is the grain for CMS drug market
- `meta.data_sources.source_name` is unique — every source registered exactly once

---

## State Transitions

**Source ingestion lifecycle**:
`registered` → `running` → `success` | `failed` | `partial`

- `registered`: row in `meta.data_sources`, `last_successful_refresh = NULL`
- `running`: run started, `last_refresh_attempt` updated
- `success`: `last_successful_refresh` updated to NOW()
- `failed`: `last_successful_refresh` unchanged; `last_refresh_status = 'failed'`
- `partial`: `last_successful_refresh` updated (partial counts as success for window calculation)

**Agent record lifecycle**:
`extracted` → `quarantined` (confidence < 0.5) | `needs_review` (0.5–0.79) | `live` (≥ 0.8)

# Column Lineage Reference

**Feature**: 019-cms-puf-platform-reconciliation
**Policy**: Zero column loss — all bronze columns must reach silver unchanged or
with documented transformation. Drops require a comment explaining why.

---

## Molecule Domain

### ChEMBL: raw → bronze → silver

| Bronze Column | Silver Column | Transformation | Notes |
|---|---|---|---|
| `chembl_id` | `chembl_id` | direct | Primary key |
| `pref_name` | `canonical_name` | `LOWER(pref_name)` | Lowercased for consistent matching |
| `molecule_type` | `molecule_type` | CASE normalization | "Small molecule" → "small_molecule" etc. |
| `max_phase` | `max_phase` | direct | Also drives `development_status` |
| `molecular_formula` | `molecular_formula` | direct | |
| `molecular_weight` | `molecular_weight` | direct | |
| `canonical_smiles` | `canonical_smiles` | direct | |
| `inchi` | `inchi` | direct | |
| `inchi_key` | `inchi_key` | direct | NULL for biologics — allowed |
| `alogp` | `alogp` | direct | Lipinski property — was dropped in pre-019, restored |
| `hba` | `hba` | direct | H-bond acceptors — restored |
| `hbd` | `hbd` | direct | H-bond donors — restored |
| `psa` | `psa` | direct | Polar surface area — restored |
| `num_ro5_violations` | `num_ro5_violations` | direct | Lipinski Rule-of-5 — restored |
| `aromatic_rings` | `aromatic_rings` | direct | Restored |
| `heavy_atoms` | `heavy_atoms` | direct | Restored |
| `first_approval` | `first_approval_year` | `::INTEGER` cast | |
| `synonyms` | — | → `mol_silver.molecule_aliases` | JSONB array expanded into alias rows |
| `cross_references` | — | DROPPED | Low-value metadata; raw_json available if needed |
| `indication_class` | — | DROPPED | Superseded by `clinical_trials.conditions` |
| `usan_stem` | — | DROPPED | Niche; available in raw |
| `therapeutic_flag` | — | DROPPED | Replaced by `development_status` |
| `prodrug` | — | DROPPED | Available in raw_json |
| `natural_product` | — | DROPPED | Available in raw_json |

**DrugBank enrichment added in silver** (not in bronze.chembl_molecules):
- `drugbank_id`, `unii`, `cas_number`, `mechanism_of_action` — from `bronze.drugbank`
- `pubchem_cid` — from `bronze.pubchem`
- `source_count`, `resolution_confidence` — computed

---

### ClinicalTrials.gov: raw → bronze → silver

| Bronze Path | Silver Column | Dropped Before 019? | Notes |
|---|---|---|---|
| `nctId` | `nct_id` | No | |
| `identificationModule.briefTitle` | `title` | No | |
| `identificationModule.officialTitle` | `official_title` | No | |
| `identificationModule.acronym` | `acronym` | **Yes — restored** | |
| `descriptionModule.briefSummary` | `brief_summary` | No | |
| `descriptionModule.detailedDescription` | `detailed_description` | No | |
| `statusModule.overallStatus` | `overall_status` | No | |
| `statusModule.whyStopped` | `why_stopped` | **Yes — restored** | Why trial discontinued |
| `statusModule.startDateStruct` | `start_date` | No | |
| `statusModule.completionDateStruct` | `completion_date` | No | |
| `statusModule.primaryCompletionDateStruct` | `primary_completion_date` | No | |
| `designModule.phases` | `phase` | No | CASE normalized |
| `designModule.studyType` | `study_type` | No | |
| `designModule.designInfo.allocation` | `allocation` | No | |
| `designModule.designInfo.interventionModel` | `intervention_model` | No | |
| `designModule.designInfo.maskingInfo.masking` | `masking` | No | |
| `designModule.enrollmentInfo.count` | `enrollment` | No | |
| `conditionsModule.conditions` | `conditions` | No | JSONB array |
| `conditionsModule.keywords` | `keywords` | No | JSONB array |
| `armsInterventionsModule.interventions` | `interventions` | No | JSONB array |
| `eligibilityModule.eligibilityCriteria` | `eligibility_criteria` | **Yes — restored** | Full text criteria |
| `eligibilityModule.minimumAge` | `minimum_age` | **Yes — restored** | e.g. "18 Years" |
| `eligibilityModule.maximumAge` | `maximum_age` | **Yes — restored** | |
| `eligibilityModule.healthyVolunteers` | `healthy_volunteers` | **Yes — restored** | "No" / "Yes" |
| `eligibilityModule.sex` | `eligibility_sex` | **Yes — restored** | |
| `sponsorCollaboratorsModule.leadSponsor.name` | `lead_sponsor` | No | |
| `sponsorCollaboratorsModule.collaborators` | `collaborators` | No | JSONB array |
| `contactsLocationsModule.centralContacts` | `central_contacts` | **Yes — restored** | JSONB array |
| `contactsLocationsModule.locations` | `locations` | **Yes — restored** | JSONB array (site data) |
| `outcomesModule.primaryOutcomes` | `primary_outcomes` | No | JSONB array |
| `outcomesModule.secondaryOutcomes` | `secondary_outcomes` | No | JSONB array |
| `hasResults` | `has_results` | No | |
| `resultsSection` | `results_section` | **Yes — restored** | Full results JSONB |
| `oversightModule.isFdaRegulatedDrug` | `fda_regulated_drug` | **Yes — restored** | |

**Added in silver** (not in bronze):
- `molecule_id` — linked via 3-tier lateral join
- `queried_drug_name` — the drug name used to query ClinicalTrials.gov API
- `trial_id` — `gen_random_uuid()` (display key, not FK target)

---

### OpenFDA FAERS: raw → bronze → silver

Silver `mol_silver.adverse_events` is an **aggregated** model (not row-level).
The grain shifts from individual FAERS report → (molecule × MedDRA PT) aggregate.

| Bronze Column | Fate | Notes |
|---|---|---|
| `drug_name` | → alias lookup → `molecule_id` | Not stored in silver; audit via aliases |
| `meddra_pts` | Expanded → `meddra_pt` (one row per PT) | JSONB array unpacked |
| `serious` | → `serious_count` (SUM) | Aggregated |
| `serious_death` | → `death_count` (SUM) | Aggregated |
| `serious_hospitalization` | → `hospitalization_count` (SUM) | Aggregated |
| `receive_date` | → `first_report_date`, `last_report_date` | MIN/MAX |
| `safety_report_id` | DROPPED (aggregated away) | Available in bronze |
| `patient_age`, `patient_sex`, etc. | DROPPED (aggregated away) | Patient-level data in bronze |

**PRR/ROR signal scores** are computed in gold, not silver.

---

### DrugBank: raw → bronze → silver

DrugBank feeds enrichment columns directly into `mol_silver.molecules` — no standalone DrugBank silver table.

| Bronze Column | Silver Destination | Notes |
|---|---|---|
| `drugbank_id` | `mol_silver.molecules.drugbank_id` | Via LEFT JOIN |
| `cas_number` | `mol_silver.molecules.cas_number` | Via LEFT JOIN |
| `unii` | `mol_silver.molecules.unii` | Via LEFT JOIN |
| `mechanism_of_action` | `mol_silver.molecules.mechanism_of_action` | Via LEFT JOIN |
| `synonyms` | `mol_silver.molecule_aliases` | Expanded into alias rows |
| `international_brands` | `mol_silver.molecule_aliases` (brand type) | Expanded |
| `products` | `mol_silver.molecule_aliases` (product type) | Expanded |
| `indication` | DROPPED | Superseded by clinical_trials.conditions |
| `drug_interactions` | DROPPED | Available in bronze; complex structure |
| `targets`, `enzymes` | → `mol_silver.molecule_targets` | Via separate pipeline |
| `atc_codes` | DROPPED | Available in bronze; not queried |
| `classification`, `categories` | DROPPED | Available in bronze; not queried |

---

## HCS Domain

### CMS NPPES + PUF sources → provider_profile

| Source | Columns Contributed | Merge Strategy |
|---|---|---|
| NPPES | `npi`, `entity_type`, `name_*`, `credential`, `taxonomy_code`, `practice_*`, `gender`, `enumeration_date` | Authoritative base |
| Physician PUF | `total_procedures`, `hcpcs_codes`, `unique_hcpcs_count` | Aggregate |
| DME PUF | `total_dme_procedures`, `dme_categories` | Aggregate |
| Mental Health PUF | `mental_health_services`, `mental_health_procedures` | Aggregate |
| Telehealth PUF | `telehealth_services`, `telehealth_procedures` | Aggregate |
| Hospice PUF | `hospice_patient_count` | Aggregate |

No columns are dropped. Non-matching NPIs produce NULLs in source-specific columns.

### CMS drug sources → drug_utilization

| Source | `code_type` | `drug_or_hcpcs_code` value | `molecule_id` linked via |
|---|---|---|---|
| Part D spending | `part_d_drug` | generic drug name | `mol_silver.molecule_aliases` |
| Medicaid drug spending | `medicaid_drug` | drug name | `mol_silver.molecule_aliases` |
| DME PUF | `dme_hcpcs` | HCPCS code | `mol_silver.hcpcs_molecule_bridge` |
| Lab services | `lab_hcpcs` | HCPCS code | `mol_silver.hcpcs_molecule_bridge` |
| Imaging PUF | `imaging_hcpcs` | HCPCS code | `mol_silver.hcpcs_molecule_bridge` |

`molecule_id` is NULL when no match is found — data is always retained regardless.

---

## Schema Redirect Reference

After 019 config.yaml update, bare logical schemas redirect to domain-prefixed physical schemas:

| SQLMesh logical | Physical PostgreSQL schema | Domain |
|---|---|---|
| `raw` | `mol_raw` | Molecules |
| `bronze` | `mol_bronze` | Molecules |
| `silver` | `mol_silver` | Molecules |
| `gold` | `mol_gold` | Molecules |
| `hcs_raw` | `hcs_raw` | Healthcare system |
| `hcs_bronze` | `hcs_bronze` | Healthcare system |
| `hcs_silver` | `hcs_silver` | Healthcare system |
| `hcs_gold` | `hcs_gold` | Healthcare system |
| `ind_silver` | `ind_silver` | Indications / disease |
| `ind_gold` | `ind_gold` | Indications / disease |
| `hcp_silver` | `hcp_silver` | HCP / KOL / researcher |
| `hcp_gold` | `hcp_gold` | HCP / KOL / researcher |

Model files do NOT need renaming — the config redirect handles physical placement.

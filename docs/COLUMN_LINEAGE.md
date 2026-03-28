# Column Lineage Reference

**Feature**: 019-cms-puf-platform-reconciliation
**Policy**: Zero data loss — all bronze columns must reach silver unchanged or with
documented transformation. A "DROPPED from silver" entry does NOT mean the data is
gone. Every dropped column is preserved in `mol_raw.*` (verbatim API response) and
in `mol_bronze.*.raw_json` (parsed JSONB). "Dropped" means: not promoted to the
conformed silver column list because a better representation already exists there.

### Drop Categories

| Category | Meaning | Data Recovery |
|---|---|---|
| **REROUTED** | Column content moved to a different, better-structured silver table | Query the target silver table directly |
| **SUPERSEDED** | A richer, more structured source covers the same information | Query the superseding silver table |
| **DERIVED** | A computed silver column replaces the raw value with a more useful form | The raw value drove the derivation; query bronze if you need the original |
| **LOW_QUERY_VALUE** | Rarely queried in practice; no silver consumer exists yet | `mol_bronze.<table>.raw_json->>'<column>'` or `mol_raw.<table>` |
| **AGGREGATED_AWAY** | Silver grain is aggregate (not row-level); column exists only at row grain | Query `mol_bronze.<table>` for row-level detail |

---

## Molecule Domain

### ChEMBL: raw → bronze → silver

| Bronze Column | Silver Column | Transformation | Notes |
|---|---|---|---|
| `chembl_id` | `chembl_id` | direct | Primary key |
| `pref_name` | `canonical_name` | direct rename | Silver uses `canonical_name` as the unified name field across all sources (ChEMBL: `pref_name`, PubChem: `iupac_name`, DrugBank: `name`). Value is NOT lowercased — casing is preserved from ChEMBL. |
| `molecule_type` | `molecule_type` | CASE normalization | "Small molecule" → "small_molecule" etc. |
| `max_phase` | `max_phase` | direct | Also drives `development_status` |
| `molecular_formula` | `molecular_formula` | direct | |
| `molecular_weight` | `molecular_weight` | direct | |
| `canonical_smiles` | `canonical_smiles` | direct | |
| `inchi` | `inchi` | direct | |
| `inchi_key` | `inchi_key` | direct | NULL for biologics — allowed |
| `alogp` | `alogp` | direct | Lipophilicity. Promoted in migration 101. PubChem `xlogp` maps to the same column. NULL for DrugBank-only molecules. |
| `hba` | `hba` | direct | H-bond acceptor count. PubChem `h_bond_acceptor_count` maps to same column. NULL for DrugBank. |
| `hbd` | `hbd` | direct | H-bond donor count. PubChem `h_bond_donor_count` maps to same column. NULL for DrugBank. |
| `psa` | `psa` | direct | Polar surface area Å². PubChem `tpsa` maps to same column. NULL for DrugBank. |
| `num_ro5_violations` | `num_ro5_violations` | direct | Lipinski Rule-of-5 violations. ChEMBL only; NULL for PubChem and DrugBank. |
| `aromatic_rings` | `aromatic_rings` | direct | Aromatic ring count. ChEMBL only; NULL for PubChem and DrugBank. |
| `heavy_atoms` | `heavy_atoms` | direct | Non-H atom count. PubChem `heavy_atom_count` maps to same column. |
| `first_approval` | `first_approval_year` | `::INTEGER` cast | |
| `synonyms` | — | **REROUTED** → `mol_silver.molecule_aliases` | JSONB array expanded into individual alias rows (one row per synonym). Rerouted because alias lookup requires `WHERE alias_name_normalized = ?` — a per-row index scan. Storing as a JSONB array in molecules would require `@>` array containment, which does not use a btree index. Full list preserved; recovery: `SELECT alias_name FROM mol_silver.molecule_aliases WHERE molecule_id = ? AND alias_type = 'synonym'`. |
| `cross_references` | — | **LOW_QUERY_VALUE** — not promoted to silver | ChEMBL cross-refs (ChEBI, PubChem, UniProt links) are superseded by `mol_silver.identifier_mappings`, which provides the same cross-database links in a normalised, queryable schema. The raw JSONB is preserved. Recovery: `mol_bronze.chembl_molecules.raw_json->'cross_references'` or `mol_raw.chembl`. |
| `indication_class` | — | **SUPERSEDED** by `mol_silver.clinical_trials.conditions` | ChEMBL's `indication_class` is a single coarse free-text string (e.g. `"Antineoplastic"`). `mol_silver.clinical_trials.conditions` provides structured, per-trial condition arrays drawn from ClinicalTrials.gov and covering the same therapeutic area with far greater specificity. Recovery: `mol_bronze.chembl_molecules.raw_json->>'indication_class'` or `mol_raw.chembl`. |
| `usan_stem` | `usan_stem` | direct | USAN stem code identifying drug class by naming suffix (e.g. `-mab`, `-tinib`). Promoted to silver in migration 100. NULL for PubChem and DrugBank sources. |
| `therapeutic_flag` | — | **DERIVED** → `development_status` | ChEMBL's `therapeutic_flag` is a binary integer (0/1) indicating whether ChEMBL has flagged the molecule as therapeutic. Silver replaces it with `development_status`, a human-readable CASE expression over `max_phase` (`'approved'`, `'phase_3'`, etc.), which is strictly more informative. The flag value is implicit in `max_phase`. Recovery: `mol_bronze.chembl_molecules.raw_json->>'therapeutic_flag'` or `mol_raw.chembl`. |
| `prodrug` | `prodrug` | direct | Boolean flag: molecule requires metabolic activation. Promoted to silver in migration 100. NULL for PubChem and DrugBank sources. |
| `natural_product` | `natural_product` | direct | Boolean flag: molecule is a natural product. Promoted to silver in migration 100. NULL for PubChem and DrugBank sources. |

**PubChem-only columns added in silver** (NULL for ChEMBL/DrugBank molecules):
- `exact_mass`, `isomeric_smiles`, `rotatable_bond_count`, `complexity`, `charge` — from `mol_bronze.pubchem`
- `mesh_headings`, `pharmacological_actions` — JSONB arrays from `mol_bronze.pubchem`

**DrugBank enrichment added in silver** via LEFT JOIN on canonical_name:
- `description`, `pharmacodynamics`, `drug_categories` — from `mol_bronze.drugbank`
- `drugbank_id`, `unii`, `cas_number` — via `mol_silver.identifier_mappings`
- `mechanism_of_action` — NULL in current DrugBank XML fetcher; will populate when fetcher extended
- Full DrugBank pharmacology → `mol_silver.drug_pharmacology` (see DrugBank section below)

**Other derived columns** (not from any single bronze source):
- `source_count`, `resolution_confidence` — computed
- `development_status` — CASE expression over `max_phase`

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
- `molecule_id` — linked via DRUG-type intervention name match against `mol_silver.molecules.canonical_name`
- `trial_id` — `gen_random_uuid()` (display key, not FK target)
- `fda_regulated_drug`, `fda_regulated_device`, `has_dmc` — extracted from `raw_json.protocolSection.oversightModule` (not typed in bronze)
- `phases_raw` — original JSONB phases array (alongside derived `phase` string)

**All previously dropped columns restored in migration 101**: `acronym`, `last_known_status`, `why_stopped`, `keywords`, `arm_groups`, `enrollment_type`, `eligibility_sex`, `minimum_age`, `maximum_age`, `healthy_volunteers`, `eligibility_criteria`, `lead_sponsor_class`, `responsible_party`, `central_contacts`, `locations`, `results_section`, `first_submit_date`, `first_post_date`, `last_update_date`.

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
| `serious_lifethreatening` | → `lifethreatening_count` (SUM) | Aggregated — added migration 101 |
| `serious_disabling` | → `disabling_count` (SUM) | Aggregated — added migration 101 |
| `serious_congenital` | → `congenital_count` (SUM) | Aggregated — added migration 101 |
| `serious_other` | → `other_serious_count` (SUM) | Aggregated — added migration 101 |
| `receive_date` | → `first_report_date`, `last_report_date` | MIN/MAX |
| `safety_report_id` | **AGGREGATED_AWAY** | Silver grain is (molecule × MedDRA PT) aggregate — individual report IDs have no meaning at this grain. Data preserved at full row-level in `mol_bronze.faers_events`. Recovery: `SELECT safety_report_id FROM mol_bronze.faers_events WHERE drug_name ILIKE ?`. |
| `patient_age`, `patient_sex`, `patient_weight`, `reporter_country`, etc. | **AGGREGATED_AWAY** | Patient-level demographic fields have no meaning in an aggregate-grain silver table. Full patient-level rows preserved in `mol_bronze.faers_events`. Recovery: query `mol_bronze.faers_events` directly, joining on `drug_name` → molecule alias lookup. |

**PRR/ROR signal scores** are computed in gold, not silver.

---

### DrugBank: raw → bronze → silver

DrugBank feeds into two silver destinations:
1. `mol_silver.molecules` — enrichment columns via LEFT JOIN on canonical_name
2. `mol_silver.drug_pharmacology` — ALL bronze columns promoted here (migration 101)

**Note**: Many DrugBank columns are NULL in bronze because the XML fetcher does not extract them (mechanism_of_action, absorption, metabolism, etc.). These are preserved as NULLs in drug_pharmacology for schema forward-compatibility.

| Bronze Column | Silver Destination | Notes |
|---|---|---|
| `drugbank_id` | `mol_silver.drug_pharmacology.drugbank_id` | Primary key |
| `name` | `mol_silver.drug_pharmacology.name` | Direct |
| `description` | `mol_silver.molecules.description` + `mol_silver.drug_pharmacology.description` | Via LEFT JOIN in molecules; full copy in drug_pharmacology |
| `indication` | `mol_silver.drug_pharmacology.indication` | **SUPERSEDED** in molecules by `clinical_trials.conditions`; preserved in drug_pharmacology |
| `pharmacodynamics` | `mol_silver.molecules.pharmacodynamics` + `mol_silver.drug_pharmacology.pharmacodynamics` | Via LEFT JOIN in molecules; full copy in drug_pharmacology |
| `categories` | `mol_silver.molecules.drug_categories` + `mol_silver.drug_pharmacology.categories` | Via LEFT JOIN in molecules; full copy in drug_pharmacology |
| `targets`, `enzymes` | `mol_silver.drug_pharmacology.targets` / `.enzymes` | Also **REROUTED** → `mol_silver.molecule_targets` for per-target indexing |
| `mechanism_of_action` | `mol_silver.drug_pharmacology.mechanism_of_action` | NULL in bronze (XML fetcher limitation) — preserved for forward-compat |
| `absorption`, `protein_binding`, `metabolism`, `half_life`, `route_of_elimination`, `clearance`, `volume_of_distribution` | `mol_silver.drug_pharmacology.*` | All NULL in bronze (XML fetcher limitation) — preserved for forward-compat |
| `toxicity` | `mol_silver.drug_pharmacology.toxicity` | NULL in bronze — forward-compat |
| `drug_interactions`, `food_interactions` | `mol_silver.drug_pharmacology.*` | NULL in bronze — forward-compat |
| `carriers`, `transporters`, `pathways` | `mol_silver.drug_pharmacology.*` | NULL in bronze — forward-compat |
| `classification`, `atc_codes`, `groups` | `mol_silver.drug_pharmacology.*` | NULL in bronze — forward-compat |
| `unii`, `external_links`, `external_identifiers` | `mol_silver.drug_pharmacology.*` | NULL in bronze |
| `fda_label`, `patents`, `calculated_properties` | `mol_silver.drug_pharmacology.*` | NULL in bronze |
| `smiles`, `inchi`, `inchi_key`, `molecular_formula`, `average_mass`, `monoisotopic_mass` | `mol_silver.drug_pharmacology.*` | NULL in bronze (XML fetcher limitation) |
| `drug_type`, `state` | `mol_silver.drug_pharmacology.*` | NULL in bronze |
| `synonyms`, `international_brands`, `products` | `mol_silver.drug_pharmacology.*` | NULL in current XML fetcher |
| `cas_number` | `mol_silver.drug_pharmacology.cas_number` | Direct |

---

### UniProt: raw → bronze → mol_silver.proteins (NEW in migration 101)

Previously: bronze existed but was entirely unconsumed by silver. All columns now promoted to `mol_silver.proteins`. molecule_id linked via `mol_silver.identifier_mappings` (identifier_type = 'uniprot').

All 27 bronze columns promoted directly. See `mol_silver.proteins` for full schema.

---

### NIH Reporter: raw → bronze → mol_silver.research_grants (NEW in migration 101)

Previously: bronze existed but was entirely unconsumed by silver. All columns now promoted to `mol_silver.research_grants`. molecule_id linked via title-match against `mol_silver.molecules.canonical_name`.

All 18 bronze columns promoted directly. See `mol_silver.research_grants` for full schema.

---

### PDB: raw → bronze → mol_silver.protein_structures (NEW in migration 101)

Previously: bronze existed but was entirely unconsumed by silver. All columns now promoted to `mol_silver.protein_structures`. molecule_id linked via ligand_id → `mol_silver.identifier_mappings` (identifier_type = 'pdb_ligand').

All 15 bronze columns promoted directly. See `mol_silver.protein_structures` for full schema.

---

### SEC EDGAR: raw → bronze → mol_silver.company_financials (NEW in migration 101)

Previously: bronze existed but was entirely unconsumed by silver. All columns now promoted to `mol_silver.company_financials`. No molecule_id linkage — SEC filings are company-level; company → drug resolution should be in gold.

All 10 bronze columns promoted directly. See `mol_silver.company_financials` for full schema.

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

### CMS Part D Prescriber PUF → hcs_silver.part_d_prescribing (NEW in feature 020)

**Source**: `hcs_raw.cms_part_d_prescriber` → `hcs_bronze.cms_part_d_prescriber` → `hcs_silver.part_d_prescribing`

Grain: `(prscrbr_npi, gnrc_name, _source_year)` — one row per prescriber × drug × year.

| Bronze Column | Silver Column | Notes |
|---|---|---|
| `prscrbr_npi` | `prscrbr_npi` | Direct — FK to `hcs_silver.provider_profile.npi` |
| `prscrbr_last_org_name` | `prscrbr_last_org_name` | Direct |
| `prscrbr_first_name` | `prscrbr_first_name` | Direct |
| `prscrbr_city` | `prscrbr_city` | Direct |
| `prscrbr_state_abrvtn` | `prscrbr_state_abrvtn` | Direct |
| `prscrbr_type` | `prscrbr_type` | Specialty description |
| `gnrc_name` | `gnrc_name` | Direct — CMS controlled vocabulary |
| `brnd_name` | `brnd_name` | Direct |
| `tot_clms` | `tot_clms` | Direct |
| `tot_30day_fills` | `tot_30day_fills` | Direct |
| `tot_day_suply` | `tot_day_suply` | Direct |
| `tot_drug_cst` | `tot_drug_cst` | Direct |
| `tot_benes` | `tot_benes` | Direct |
| `ge65_sprsn_flag` | `ge65_sprsn_flag` | CMS privacy suppression flag ('Y' = <11 benes) |
| `ge65_tot_clms`, `ge65_tot_30day_fills`, `ge65_tot_drug_cst`, `ge65_tot_day_suply`, `ge65_tot_benes` | same | Direct (NULL when suppressed) |
| `ge65_bene_sprsn_flag` | `ge65_bene_sprsn_flag` | Secondary suppression flag |
| `_source_year` | `_source_year` | Direct |
| `prscrbr_state_fips`, `prscrbr_type_src` | — | **LOW_QUERY_VALUE** — in bronze, not promoted to silver |

**Added in silver** (not in bronze):
- `molecule_id` — linked via `gnrc_name → mol_silver.molecule_aliases.alias_name_normalized` (confidence 0.85; CMS generic names are a controlled vocabulary)
- `link_confidence`, `matched_alias_type`, `molecule_resolved` — resolution audit columns

---

### CMS Open Payments drug slots → hcs_silver.open_payments_drug_linkage (NEW in feature 020)

**Source**: `hcs_raw.cms_open_payments` → `hcs_bronze.cms_open_payments` → `hcs_silver.open_payments_drug_linkage`

Grain: `(record_id, drug_slot, _source_year)` — one row per drug per payment.

Migration 089 added 5 drug name slots and 5 NDC slots to `hcs_raw.cms_open_payments`:

| Bronze Column (from migration 089) | Silver Column | Notes |
|---|---|---|
| `name_of_drug_or_biological_or_device_or_medical_supply_1..5` | `drug_name` (unnested per slot) | CMS verbatim drug name; UNNEST across 5 slots |
| `drug_name_1_normalized..5_normalized` | `drug_name_normalized` | GENERATED ALWAYS column on raw table |
| `associated_drug_or_biological_ndc_1..5` | `ndc` (per slot) | NDC for structural bridge |
| `covered_recipient_type`, `physician_profile_id`, `physician_first_name`, `physician_last_name`, `physician_specialty` | same | Direct |
| `applicable_manufacturer_or_gpo_name` | same | Direct |
| `total_amount_of_payment_usdollars`, `date_of_payment`, `nature_of_payment_or_transfer_of_value` | same | Direct |
| `recipient_state`, `_source_year`, `record_id` | same | Direct |

**Added in silver** (entity linking):
- `molecule_id` — Path A: NDC → `mol_silver.ndc_molecule_bridge` (confidence 0.95); Path B: `drug_name_normalized → mol_silver.molecule_aliases` (confidence 0.75, fallback when NDC absent)
- `link_confidence`, `link_strategy`, `molecule_resolved` — resolution audit columns
- `drug_slot` — which of the 5 CMS drug slots this row came from

---

## Schema Redirect Reference

SQLMesh `physical_schema_mapping` (in `src/dk_data/sqlmesh/config.yaml`) redirects bare logical schema names to domain-prefixed physical schemas. **Model files do not need renaming** — the redirect handles physical placement.

| SQLMesh model declares | Lands in (physical PostgreSQL schema) | Domain |
|---|---|---|
| `raw.*` | `mol_raw.*` | Molecules |
| `bronze.*` | `mol_bronze.*` | Molecules |
| `silver.*` | `mol_silver.*` | Molecules |
| `gold.*` | `mol_gold.*` | Molecules |
| `mol_raw.*` | `mol_raw.*` | Molecules (explicit) |
| `mol_bronze.*` | `mol_bronze.*` | Molecules (explicit) |
| `mol_silver.*` | `mol_silver.*` | Molecules (explicit) |
| `mol_gold.*` | `mol_gold.*` | Molecules (explicit) |
| `hcs_raw.*` | `hcs_raw.*` | Healthcare system |
| `hcs_bronze.*` | `hcs_bronze.*` | Healthcare system |
| `hcs_silver.*` | `hcs_silver.*` | Healthcare system |
| `hcs_gold.*` | `hcs_gold.*` | Healthcare system |
| `ind_silver.*` | `ind_silver.*` | Indications / disease |
| `ind_gold.*` | `ind_gold.*` | Indications / disease |
| `hcp_silver.*` | `hcp_silver.*` | HCP / KOL / researcher |
| `hcp_gold.*` | `hcp_gold.*` | HCP / KOL / researcher |

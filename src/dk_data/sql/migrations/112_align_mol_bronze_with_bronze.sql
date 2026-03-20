-- Migration 112: Align mol_bronze tables with bronze tables
-- Ensures mol_bronze has ALL columns from bronze so we can use mol_bronze exclusively
-- and entity_linking never needs to reference non-mol_ tables.
-- Rule: NO DATA LOSS — every column from bronze must exist in mol_bronze.

-- ═══ clinicaltrials ═══
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "org_study_id" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "acronym" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "last_known_status" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "study_first_submit_date" date;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "study_first_post_date" date;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "last_update_post_date" date;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "collaborators" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "phases" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "allocation" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "intervention_model" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "primary_purpose" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "masking" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "arms_groups" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "primary_outcomes" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "secondary_outcomes" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "eligibility_criteria" text;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "sex" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "minimum_age" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "maximum_age" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "healthy_volunteers" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "central_contacts" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "keywords" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "mesh_terms" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "results_section" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "fda_regulated_drug" boolean;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "fda_regulated_device" boolean;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "ipd_sharing" character varying;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "has_results" boolean;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "condition_browse" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "intervention_browse" jsonb;
ALTER TABLE mol_bronze.clinicaltrials ADD COLUMN IF NOT EXISTS "references" jsonb;

-- ═══ openfda_faers ═══
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "serious_disabling" integer;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "serious_life_threatening" integer;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "serious_other" integer;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "patient_drug" jsonb;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "patient_reaction" jsonb;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "sender_organization" character varying;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "receiver_organization" character varying;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "companynumb" character varying;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "occurrence_country" character varying;
ALTER TABLE mol_bronze.openfda_faers ADD COLUMN IF NOT EXISTS "safety_report_version" integer;

-- ═══ openfda_labels ═══
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "dosage_and_administration" text;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "warnings_and_cautions" text;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "clinical_pharmacology" text;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "mechanism_of_action" text;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "pharmacodynamics" text;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "pharmacokinetics" text;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "clinical_studies" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "overdosage" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "description" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "how_supplied" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "geriatric_use" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "pediatric_use" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "pregnancy" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "storage_and_handling" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "use_in_specific_populations" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "dosage_forms_and_strengths" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "openfda_rxcui" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "openfda_unii" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "openfda_pharm_class_epc" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "openfda_pharm_class_moa" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "openfda_application_number" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "adverse_reactions_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "clinical_studies_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "clinical_pharmacology_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "dosage_and_administration_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "pharmacokinetics_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "how_supplied_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "storage_and_handling_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "references" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "nonclinical_toxicology" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "information_for_patients" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "spl_medguide" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "spl_medguide_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "spl_patient_package_insert" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "spl_patient_package_insert_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "laboratory_tests" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "pharmacogenomics" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "drug_interactions_table" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "version" integer;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "openfda" jsonb;
ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS "recent_major_changes" jsonb;

-- Backfill mol_bronze from bronze for data that exists
INSERT INTO mol_bronze.clinicaltrials (nct_id, acronym, eligibility_criteria, allocation, intervention_model, masking,
  primary_outcomes, secondary_outcomes, arms_groups, has_results, results_section, fda_regulated_drug, fda_regulated_device,
  "references", ipd_sharing, keywords, phases, sex, minimum_age, maximum_age, healthy_volunteers, central_contacts, mesh_terms,
  condition_browse, intervention_browse, last_update_post_date)
SELECT nct_id, acronym, eligibility_criteria, allocation, intervention_model, masking,
  primary_outcomes, secondary_outcomes, arms_groups, has_results, results_section, fda_regulated_drug, fda_regulated_device,
  "references", ipd_sharing, keywords, phases, sex, minimum_age, maximum_age, healthy_volunteers, central_contacts, mesh_terms,
  condition_browse, intervention_browse, last_update_post_date
FROM bronze.clinicaltrials
ON CONFLICT (nct_id) DO UPDATE SET
  acronym = COALESCE(EXCLUDED.acronym, mol_bronze.clinicaltrials.acronym),
  eligibility_criteria = COALESCE(EXCLUDED.eligibility_criteria, mol_bronze.clinicaltrials.eligibility_criteria),
  allocation = COALESCE(EXCLUDED.allocation, mol_bronze.clinicaltrials.allocation),
  intervention_model = COALESCE(EXCLUDED.intervention_model, mol_bronze.clinicaltrials.intervention_model),
  masking = COALESCE(EXCLUDED.masking, mol_bronze.clinicaltrials.masking),
  primary_outcomes = COALESCE(EXCLUDED.primary_outcomes, mol_bronze.clinicaltrials.primary_outcomes),
  secondary_outcomes = COALESCE(EXCLUDED.secondary_outcomes, mol_bronze.clinicaltrials.secondary_outcomes),
  arms_groups = COALESCE(EXCLUDED.arms_groups, mol_bronze.clinicaltrials.arms_groups),
  has_results = COALESCE(EXCLUDED.has_results, mol_bronze.clinicaltrials.has_results),
  results_section = COALESCE(EXCLUDED.results_section, mol_bronze.clinicaltrials.results_section),
  fda_regulated_drug = COALESCE(EXCLUDED.fda_regulated_drug, mol_bronze.clinicaltrials.fda_regulated_drug),
  fda_regulated_device = COALESCE(EXCLUDED.fda_regulated_device, mol_bronze.clinicaltrials.fda_regulated_device),
  "references" = COALESCE(EXCLUDED."references", mol_bronze.clinicaltrials."references"),
  ipd_sharing = COALESCE(EXCLUDED.ipd_sharing, mol_bronze.clinicaltrials.ipd_sharing);

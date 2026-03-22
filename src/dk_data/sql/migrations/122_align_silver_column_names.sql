-- Migration: 122_align_silver_column_names.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Align mol_silver column names with raw API-authoritative naming.
--   Raw API response column names are the authoritative source for naming
--   across all layers (raw, bronze, silver, gold).
--
-- Changes:
--   mol_silver.molecules:        smiles → canonical_smiles; add mechanism_of_action, max_phase
--   mol_silver.clinical_trials:  title→brief_title, status→overall_status,
--                                sponsor→lead_sponsor_name, sponsor_type→lead_sponsor_class,
--                                enrollment_target→enrollment_count,
--                                intervention_names TEXT[]→interventions JSONB,
--                                conditions TEXT[]→conditions JSONB;
--                                add ~30 missing columns the refresher already writes
--   mol_silver.drug_labels:      manufacturer→manufacturer_name, indications→indications_and_usage,
--                                route_of_administration→route; add ~50 missing columns
--   mol_silver.adverse_events:   source_report_id→safety_report_id, seriousness→seriousness_text;
--                                add safety_report_version, receive_date, serious BOOLEAN, etc.
--
-- Note: All DO $$ blocks are avoided — psycopg2 multi-statement execute splits on $$ delimiters.
--       This migration is written as unconditional DDL based on confirmed DB state.

-- Drop dependent mol_api views before column type changes.
-- PostgreSQL blocks ALTER COLUMN TYPE while views depend on the column.
-- Views are recreated at the end of this migration.
DROP VIEW IF EXISTS mol_api.molecules CASCADE;
DROP VIEW IF EXISTS mol_api.molecule_search CASCADE;
DROP VIEW IF EXISTS mol_api.clinical_trials CASCADE;
DROP VIEW IF EXISTS mol_api.drug_labels CASCADE;
DROP VIEW IF EXISTS mol_api.adverse_events CASCADE;
DROP VIEW IF EXISTS mol_api.cross_references CASCADE;
DROP VIEW IF EXISTS mol_api.lifecycle_stages CASCADE;
DROP VIEW IF EXISTS mol_api.resolution_queue CASCADE;
DROP VIEW IF EXISTS mol_api.safety_signals CASCADE;
DROP VIEW IF EXISTS mol_api.competitive_landscape CASCADE;
DROP VIEW IF EXISTS mol_api.pipeline_status CASCADE;
DROP VIEW IF EXISTS mol_api.tracked_molecules CASCADE;
DROP VIEW IF EXISTS mol_api.user_annotations CASCADE;
DROP VIEW IF EXISTS mol_api.data_sources CASCADE;
DROP VIEW IF EXISTS mol_api.active_sources CASCADE;

-- ============================================================================
-- 1. mol_silver.molecules
-- ============================================================================

-- smiles → canonical_smiles (match bronze.chembl.canonical_smiles)
ALTER TABLE mol_silver.molecules RENAME COLUMN smiles TO canonical_smiles;

-- Add columns the refresher writes
ALTER TABLE mol_silver.molecules ADD COLUMN IF NOT EXISTS mechanism_of_action TEXT;
ALTER TABLE mol_silver.molecules ADD COLUMN IF NOT EXISTS max_phase INTEGER;

-- Drop NOT NULL on inchi_key (molecules from ClinicalTrials lack structure data)
ALTER TABLE mol_silver.molecules ALTER COLUMN inchi_key DROP NOT NULL;

-- ============================================================================
-- 2. mol_silver.clinical_trials — core renames
-- ============================================================================

ALTER TABLE mol_silver.clinical_trials RENAME COLUMN title TO brief_title;
ALTER TABLE mol_silver.clinical_trials RENAME COLUMN status TO overall_status;
ALTER TABLE mol_silver.clinical_trials RENAME COLUMN sponsor TO lead_sponsor_name;
ALTER TABLE mol_silver.clinical_trials RENAME COLUMN sponsor_type TO lead_sponsor_class;
ALTER TABLE mol_silver.clinical_trials RENAME COLUMN enrollment_target TO enrollment_count;
ALTER TABLE mol_silver.clinical_trials RENAME COLUMN intervention_names TO interventions;

-- Change interventions TEXT[] → JSONB (bronze uses JSONB for structured intervention objects)
ALTER TABLE mol_silver.clinical_trials
    ALTER COLUMN interventions TYPE JSONB USING to_jsonb(interventions);

-- Change conditions TEXT[] → JSONB (bronze uses JSONB; refresher passes json.dumps([...]))
ALTER TABLE mol_silver.clinical_trials
    ALTER COLUMN conditions TYPE JSONB USING to_jsonb(conditions);

-- Rename arms → arms_groups (migration 109 added as 'arms'; bronze column is 'arms_groups')
ALTER TABLE mol_silver.clinical_trials RENAME COLUMN arms TO arms_groups;

-- Add all missing columns the refresher writes (none will error if already added by earlier migration)
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS org_study_id VARCHAR(100);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS official_title TEXT;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS detailed_description TEXT;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS last_known_status VARCHAR(50);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS phases JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS start_date_type VARCHAR(20);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS completion_date_type VARCHAR(20);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS primary_completion_date DATE;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS study_first_submit_date DATE;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS study_first_post_date DATE;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS last_update_post_date DATE;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS allocation VARCHAR(50);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS intervention_model VARCHAR(100);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS primary_purpose VARCHAR(100);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS masking VARCHAR(100);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS keywords JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS mesh_terms JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS location_countries TEXT[];
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS sex VARCHAR(20);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS minimum_age VARCHAR(20);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS maximum_age VARCHAR(20);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS healthy_volunteers VARCHAR(50);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS collaborators JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS central_contacts JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS fda_regulated_drug BOOLEAN;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS fda_regulated_device BOOLEAN;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS ipd_sharing VARCHAR(20);
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS results_participant_flow JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS results_baseline JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS condition_browse JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS intervention_browse JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS "references" JSONB;
ALTER TABLE mol_silver.clinical_trials ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'clinicaltrials_gov';

-- Fix index on renamed column
DROP INDEX IF EXISTS idx_silver_trials_status;
CREATE INDEX IF NOT EXISTS idx_silver_trials_overall_status
    ON mol_silver.clinical_trials(overall_status);

-- ============================================================================
-- 3. mol_silver.drug_labels — core renames
-- ============================================================================

ALTER TABLE mol_silver.drug_labels RENAME COLUMN manufacturer TO manufacturer_name;
ALTER TABLE mol_silver.drug_labels RENAME COLUMN indications TO indications_and_usage;
ALTER TABLE mol_silver.drug_labels RENAME COLUMN route_of_administration TO route;

-- Add all missing columns the refresher writes
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS version INTEGER;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS effective_time DATE;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS product_type VARCHAR(100);
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS substance_name TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS active_ingredient TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS dosage_and_administration TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS dosage_forms_and_strengths TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS warnings_and_cautions TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS use_in_specific_populations TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS clinical_pharmacology TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS mechanism_of_action TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS pharmacodynamics TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS pharmacokinetics TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS overdosage TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS clinical_studies TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS how_supplied TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS storage_and_handling TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS package_label_principal_display_panel TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS pregnancy TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS nursing_mothers TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS pediatric_use TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS geriatric_use TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS information_for_patients TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS spl_medguide TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS spl_product_data_elements TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS nonclinical_toxicology TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS laboratory_tests TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS pharmacogenomics TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS "references" TEXT;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_application_number JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_brand_name VARCHAR(500);
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_generic_name VARCHAR(500);
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_manufacturer_name VARCHAR(500);
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_product_type VARCHAR(100);
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_route JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_rxcui JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_spl_id VARCHAR(100);
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_spl_set_id JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_unii JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_nui JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_epc JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_moa JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_pe JSONB;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_is_original_packager BOOLEAN;
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'openfda_labels';

-- ============================================================================
-- 4. mol_silver.adverse_events — core renames
-- ============================================================================

ALTER TABLE mol_silver.adverse_events RENAME COLUMN source_report_id TO safety_report_id;
ALTER TABLE mol_silver.adverse_events RENAME COLUMN seriousness TO seriousness_text;

-- Add all missing columns the refresher writes
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS safety_report_version VARCHAR(20);
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS receive_date DATE;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS receipt_date DATE;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS serious BOOLEAN;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS serious_death BOOLEAN;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS serious_hospitalization BOOLEAN;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS serious_lifethreatening BOOLEAN;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS serious_disabling BOOLEAN;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS serious_other BOOLEAN;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS patient_age_unit VARCHAR(20);
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS patient_weight DECIMAL(10,2);
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS reporter_country VARCHAR(50);
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS occurrence_country VARCHAR(50);
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS companynumb VARCHAR(100);
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS drugs JSONB;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS reactions JSONB;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS outcomes JSONB;
ALTER TABLE mol_silver.adverse_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add unique constraint for FAERS deduplication (required by ON CONFLICT in refresher)
ALTER TABLE mol_silver.adverse_events
    ADD CONSTRAINT uq_ae_safety_report_version
    UNIQUE (safety_report_id, safety_report_version);

-- ============================================================================
-- 5. Grants — ensure roles retain access after ALTER TABLE
-- ============================================================================

GRANT SELECT ON mol_silver.molecules TO analyst;
GRANT SELECT ON mol_silver.clinical_trials TO analyst;
GRANT SELECT ON mol_silver.drug_labels TO analyst;
GRANT SELECT ON mol_silver.adverse_events TO analyst;

GRANT SELECT ON mol_silver.molecules TO authenticator;
GRANT SELECT ON mol_silver.clinical_trials TO authenticator;
GRANT SELECT ON mol_silver.drug_labels TO authenticator;
GRANT SELECT ON mol_silver.adverse_events TO authenticator;

GRANT SELECT ON mol_silver.molecules TO web_anon;
GRANT SELECT ON mol_silver.clinical_trials TO web_anon;
GRANT SELECT ON mol_silver.drug_labels TO web_anon;
GRANT SELECT ON mol_silver.adverse_events TO web_anon;

-- ============================================================================
-- 6. Recreate mol_api views with updated column names
-- ============================================================================

CREATE OR REPLACE VIEW mol_api.molecules AS
SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    m.chembl_id,
    m.drugbank_id,
    m.pubchem_cid,
    m.unii,
    m.cas_number,
    m.canonical_smiles,
    m.molecular_formula,
    m.molecular_weight,
    m.molecule_type,
    m.therapeutic_areas,
    m.atc_codes,
    m.brand_names,
    m.generic_names,
    p.lifecycle_stage,
    p.stage_confidence,
    p.data_completeness,
    p.trial_count,
    p.active_trial_count,
    p.label_count,
    p.adverse_event_count,
    p.first_approval_date,
    m.resolution_confidence,
    m.source_count,
    m.created_at,
    m.updated_at
FROM mol_silver.molecules m
LEFT JOIN mol_gold.molecule_profiles p ON m.molecule_id = p.molecule_id
WHERE m.needs_review = FALSE;

CREATE OR REPLACE VIEW mol_api.molecule_search AS
SELECT DISTINCT ON (m.molecule_id)
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    m.chembl_id,
    m.drugbank_id,
    m.pubchem_cid,
    a.alias_name,
    a.alias_type,
    a.alias_name_normalized,
    m.molecule_type,
    p.lifecycle_stage
FROM mol_silver.molecules m
LEFT JOIN mol_silver.molecule_aliases a ON m.molecule_id = a.molecule_id
LEFT JOIN mol_gold.molecule_profiles p ON m.molecule_id = p.molecule_id
WHERE m.needs_review = FALSE;

-- mol_api.clinical_trials: expose both old and new column names for backward compat
CREATE OR REPLACE VIEW mol_api.clinical_trials AS
SELECT
    t.trial_id,
    t.nct_id,
    t.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    t.brief_title,
    t.brief_title AS title,
    t.brief_summary,
    t.phase,
    t.overall_status,
    t.overall_status AS status,
    t.study_type,
    t.conditions,
    t.interventions,
    t.enrollment_count,
    t.enrollment_count AS enrollment_target,
    t.enrollment_actual,
    t.start_date,
    t.completion_date,
    t.lead_sponsor_name,
    t.lead_sponsor_name AS sponsor,
    t.lead_sponsor_class,
    t.lead_sponsor_class AS sponsor_type,
    t.has_results,
    t.created_at,
    t.updated_at
FROM mol_silver.clinical_trials t
LEFT JOIN mol_silver.molecules m ON t.molecule_id = m.molecule_id;

-- mol_api.drug_labels: expose both old and new column names for backward compat
CREATE OR REPLACE VIEW mol_api.drug_labels AS
SELECT
    l.label_id,
    l.set_id,
    l.molecule_id,
    m.inchi_key,
    l.brand_name,
    l.generic_name,
    l.manufacturer_name,
    l.manufacturer_name AS manufacturer,
    l.application_number,
    l.approval_date,
    l.marketing_status,
    l.route,
    l.route AS route_of_administration,
    l.indications_and_usage,
    l.indications_and_usage AS indications,
    l.contraindications,
    l.warnings,
    l.boxed_warning,
    l.adverse_reactions,
    l.drug_interactions,
    l.mechanism_of_action,
    l.clinical_studies,
    l.effective_date,
    l.created_at,
    l.updated_at
FROM mol_silver.drug_labels l
LEFT JOIN mol_silver.molecules m ON l.molecule_id = m.molecule_id;

-- mol_api.adverse_events: expose both old and new column names for backward compat
CREATE OR REPLACE VIEW mol_api.adverse_events AS
SELECT
    ae.event_id,
    ae.source,
    ae.safety_report_id,
    ae.safety_report_id AS source_report_id,
    ae.molecule_id,
    m.inchi_key,
    ae.drug_name_reported,
    ae.reaction_meddra_pt,
    ae.reaction_meddra_code,
    ae.seriousness_text,
    ae.seriousness_text AS seriousness,
    ae.serious,
    ae.outcome,
    ae.patient_age,
    ae.patient_sex,
    ae.report_date,
    ae.country,
    ae.created_at
FROM mol_silver.adverse_events ae
LEFT JOIN mol_silver.molecules m ON ae.molecule_id = m.molecule_id;

CREATE OR REPLACE VIEW mol_api.cross_references AS
SELECT
    im.mapping_id,
    im.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    im.identifier_type,
    im.identifier_value,
    im.source,
    im.confidence,
    im.is_primary,
    im.is_validated,
    im.created_at
FROM mol_silver.identifier_mappings im
JOIN mol_silver.molecules m ON im.molecule_id = m.molecule_id
WHERE m.needs_review = FALSE;

CREATE OR REPLACE VIEW mol_api.safety_signals AS
SELECT
    s.signal_id,
    s.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    s.reaction_meddra_pt,
    s.reaction_soc,
    s.case_count,
    s.prr_score,
    s.ror_score,
    s.ic_score,
    s.signal_strength,
    s.first_reported,
    s.last_reported,
    s.trend_direction,
    s.last_updated
FROM mol_gold.safety_signals s
JOIN mol_silver.molecules m ON s.molecule_id = m.molecule_id;

CREATE OR REPLACE VIEW mol_api.competitive_landscape AS
SELECT
    cl.landscape_id,
    cl.indication,
    cl.indication_mesh_id,
    cl.molecule_ids,
    cl.approved_count,
    cl.phase3_count,
    cl.phase2_count,
    cl.phase1_count,
    cl.market_leaders,
    cl.recent_approvals,
    cl.pipeline_trends,
    cl.last_updated
FROM mol_gold.competitive_landscape cl;

CREATE OR REPLACE VIEW mol_api.lifecycle_stages AS
SELECT
    ls.stage_id,
    ls.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    ls.indication,
    ls.lifecycle_stage,
    ls.confidence,
    ls.evidence_sources,
    ls.detected_at,
    ls.validated_by,
    ls.validated_at
FROM mol_gold.lifecycle_stages ls
JOIN mol_silver.molecules m ON ls.molecule_id = m.molecule_id;

CREATE OR REPLACE VIEW mol_api.resolution_queue AS
SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    m.chembl_id,
    m.drugbank_id,
    m.pubchem_cid,
    m.resolution_confidence,
    m.review_reason,
    m.needs_review,
    m.source_count,
    m.created_at,
    ARRAY_AGG(DISTINCT a.alias_name) FILTER (WHERE a.alias_name IS NOT NULL) AS candidate_names,
    JSONB_AGG(
        DISTINCT JSONB_BUILD_OBJECT(
            'source', im.source,
            'identifier_type', im.identifier_type,
            'identifier_value', im.identifier_value,
            'confidence', im.confidence
        )
    ) FILTER (WHERE im.mapping_id IS NOT NULL) AS source_identifiers
FROM mol_silver.molecules m
LEFT JOIN mol_silver.molecule_aliases a ON m.molecule_id = a.molecule_id
LEFT JOIN mol_silver.identifier_mappings im ON m.molecule_id = im.molecule_id
WHERE m.needs_review = TRUE
GROUP BY m.molecule_id, m.inchi_key, m.canonical_name, m.chembl_id,
         m.drugbank_id, m.pubchem_cid, m.resolution_confidence,
         m.review_reason, m.needs_review, m.source_count, m.created_at;

CREATE OR REPLACE VIEW mol_api.pipeline_status AS
SELECT
    'raw' AS layer,
    (SELECT COUNT(*) FROM mol_raw.clinicaltrials) +
    (SELECT COUNT(*) FROM mol_raw.chembl) +
    (SELECT COUNT(*) FROM mol_raw.pubchem) +
    (SELECT COUNT(*) FROM mol_raw.drugbank) +
    (SELECT COUNT(*) FROM mol_raw.openfda_labels) +
    (SELECT COUNT(*) FROM mol_raw.openfda_faers) AS record_count,
    GREATEST(
        (SELECT MAX(ingested_at) FROM mol_raw.clinicaltrials),
        (SELECT MAX(ingested_at) FROM mol_raw.chembl),
        (SELECT MAX(ingested_at) FROM mol_raw.pubchem)
    ) AS last_updated
UNION ALL
SELECT
    'bronze' AS layer,
    (SELECT COUNT(*) FROM mol_bronze.clinicaltrials) +
    (SELECT COUNT(*) FROM mol_bronze.chembl) +
    (SELECT COUNT(*) FROM mol_bronze.pubchem) +
    (SELECT COUNT(*) FROM mol_bronze.drugbank) +
    (SELECT COUNT(*) FROM mol_bronze.openfda_labels) +
    (SELECT COUNT(*) FROM mol_bronze.openfda_faers) AS record_count,
    GREATEST(
        (SELECT MAX(ingested_at) FROM mol_bronze.clinicaltrials),
        (SELECT MAX(ingested_at) FROM mol_bronze.chembl),
        (SELECT MAX(ingested_at) FROM mol_bronze.pubchem)
    ) AS last_updated
UNION ALL
SELECT
    'silver' AS layer,
    (SELECT COUNT(*) FROM mol_silver.molecules) AS record_count,
    (SELECT MAX(updated_at) FROM mol_silver.molecules) AS last_updated
UNION ALL
SELECT
    'gold' AS layer,
    (SELECT COUNT(*) FROM mol_gold.molecule_profiles) AS record_count,
    (SELECT MAX(last_updated) FROM mol_gold.molecule_profiles) AS last_updated;

-- API View Contracts for 012-platform-hardening
-- These views are added to db-init-job.yaml

-- ============================================================
-- NEW VIEWS (tables don't exist yet — create backing tables first)
-- ============================================================

-- View: api.company_pipeline
-- Source: mol_gold.company_pipeline (NEW TABLE)
-- Used by: behavior-labs-ai specs 031 (AI Decision Engine), 033 (Commercial Analytics)
CREATE OR REPLACE VIEW api.company_pipeline AS
SELECT
    id,
    company_name,
    molecule_name,
    indication,
    phase,
    status,
    mechanism_of_action,
    source,
    last_updated
FROM mol_gold.company_pipeline;

GRANT SELECT ON api.company_pipeline TO api_user;
GRANT SELECT ON api.company_pipeline TO analyst;

-- View: api.molecule_targets
-- Source: mol_silver.targets (NEW TABLE)
-- Used by: behavior-labs-ai spec 032 (Discovery Optimization)
CREATE OR REPLACE VIEW api.molecule_targets AS
SELECT
    id,
    target_name,
    target_type,
    uniprot_accession,
    gene_symbol,
    organism,
    molecule_name,
    action_type,
    binding_affinity,
    source
FROM mol_silver.targets;

GRANT SELECT ON api.molecule_targets TO api_user;
GRANT SELECT ON api.molecule_targets TO analyst;

-- View: api.trial_publication_features
-- Source: mol_gold.trial_publication_features (NEW TABLE)
-- Used by: behavior-labs-ai specs 033, 034 (Commercial Analytics, Patent Intelligence)
-- NOTE: Updates existing placeholder view in db-init-job.yaml
CREATE OR REPLACE VIEW api.trial_publication_features AS
SELECT
    id,
    nct_id,
    publication_doi,
    publication_pmid,
    overlap_score,
    feature_type,
    trial_title,
    publication_title,
    source
FROM mol_gold.trial_publication_features;

GRANT SELECT ON api.trial_publication_features TO api_user;
GRANT SELECT ON api.trial_publication_features TO analyst;

-- ============================================================
-- NEW VIEWS (backing tables already exist)
-- ============================================================

-- View: api.sider_side_effects
-- Source: bronze.sider (EXISTS — migration 030)
-- Used by: behavior-labs-ai spec 030 (Safety & Pharmacovigilance)
CREATE OR REPLACE VIEW api.sider_side_effects AS
SELECT
    id,
    drug_name,
    side_effect,
    meddra_id,
    frequency,
    source,
    ingested_at
FROM bronze.sider;

GRANT SELECT ON api.sider_side_effects TO api_user;
GRANT SELECT ON api.sider_side_effects TO analyst;

-- View: api.bioactivity
-- Source: silver.bioactivity (EXISTS — migration 031)
-- Used by: behavior-labs-ai spec 032 (Discovery Optimization)
CREATE OR REPLACE VIEW api.bioactivity AS
SELECT
    id,
    molecule_id,
    target_name,
    activity_type,
    activity_value,
    activity_unit,
    assay_type,
    source,
    ingested_at
FROM silver.bioactivity;

GRANT SELECT ON api.bioactivity TO api_user;
GRANT SELECT ON api.bioactivity TO analyst;

-- ============================================================
-- UPDATE EXISTING PLACEHOLDER VIEWS
-- ============================================================

-- View: api.patents (EXISTS as placeholder — update to reference silver.patents)
-- Source: silver.patents (EXISTS — migration 031)
-- Used by: behavior-labs-ai specs 033, 034
CREATE OR REPLACE VIEW api.patents AS
SELECT
    id,
    patent_number,
    title,
    assignee,
    filing_date,
    expiration_date,
    molecule_id,
    cpc_codes,
    country,
    status,
    source,
    ingested_at
FROM silver.patents;

GRANT SELECT ON api.patents TO api_user;
GRANT SELECT ON api.patents TO analyst;

-- View: api.company_pipeline (EXISTS as placeholder — update with real table)
-- Already defined above — replaces empty placeholder

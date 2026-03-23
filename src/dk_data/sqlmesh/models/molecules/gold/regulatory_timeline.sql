-- SQLMesh Model: Gold Regulatory Timeline
-- Cross-source regulatory decision history per molecule
-- Uses actual column names from bronze sources (no renames)

MODEL (
    name mol_gold.regulatory_timeline,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, agency, decision_id)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (agency))
    ),
    grain (molecule_id, agency, decision_id)
);

-- Sources:
--   1. mol_silver.drug_labels       → FDA label effective dates (direct molecule_id join)
--   2. mol_silver.patent_exclusivities → Orange/Purple Book approval + exclusivity (name-joined via molecules)
--   3. mol_silver.ema_regulatory    → EMA authorization dates (name-joined via molecules)
-- Note: patent_exclusivities.molecule_id and ema_regulatory.molecule_id are NULL until entity linking runs,
--       so we use case-insensitive name matching via mol_silver.molecules.canonical_name.

WITH

-- ── Source 1: FDA label effective dates (has direct molecule_id) ─────────────
fda_label_events AS (
    SELECT
        dl.molecule_id,
        'FDA'                                                                  AS agency,
        COALESCE(dl.brand_name, dl.generic_name, 'FDA Label')                 AS drug_name,
        dl.generic_name                                                        AS active_substance,
        NULL::TEXT                                                             AS indication,
        'label_effective'                                                      AS decision,
        dl.effective_date::DATE                                                AS decision_date,
        NULL::TEXT                                                             AS therapeutic_area,
        NULL::TEXT                                                             AS recommendation,
        dl.set_id                                                              AS decision_id,
        NULL::TEXT                                                             AS product_number,
        COALESCE(dl.brand_name, dl.generic_name)                              AS product_name,
        dl.generic_name                                                        AS inn,
        NULL::TEXT                                                             AS atc_code,
        dl.manufacturer_name                                                   AS marketing_authorization_holder,
        'Labeled'                                                              AS authorization_status,
        dl.effective_date::DATE                                                AS authorization_date,
        NULL::TEXT                                                             AS epar_url,
        NULL::TEXT                                                             AS guidance_id,
        NULL::TEXT                                                             AS title,
        NULL::TEXT                                                             AS url,
        NULL::NUMERIC                                                          AS icer_value
    FROM mol_silver.drug_labels dl
    WHERE dl.effective_date IS NOT NULL
      AND dl.molecule_id IS NOT NULL
),

-- ── Source 2a: Orange/Purple Book NDA/BLA approvals (name-joined) ───────────
ob_approval_events AS (
    SELECT DISTINCT ON (m.molecule_id, pe.application_number)
        m.molecule_id,
        'FDA'                                                                  AS agency,
        COALESCE(pe.trade_name, pe.generic_name)                              AS drug_name,
        pe.generic_name                                                        AS active_substance,
        NULL::TEXT                                                             AS indication,
        CASE WHEN pe.source_book = 'purple_book' THEN 'BLA_approval'
             ELSE 'NDA_approval' END                                           AS decision,
        pe.approval_date::DATE                                                 AS decision_date,
        NULL::TEXT                                                             AS therapeutic_area,
        pe.applicant                                                           AS recommendation,
        pe.application_number                                                  AS decision_id,
        pe.product_number,
        COALESCE(pe.trade_name, pe.generic_name)                              AS product_name,
        pe.generic_name                                                        AS inn,
        NULL::TEXT                                                             AS atc_code,
        pe.applicant                                                           AS marketing_authorization_holder,
        'Approved'                                                             AS authorization_status,
        pe.approval_date::DATE                                                 AS authorization_date,
        NULL::TEXT                                                             AS epar_url,
        NULL::TEXT                                                             AS guidance_id,
        NULL::TEXT                                                             AS title,
        NULL::TEXT                                                             AS url,
        NULL::NUMERIC                                                          AS icer_value
    FROM mol_silver.patent_exclusivities pe
    JOIN mol_silver.molecules m
      ON m.canonical_name ILIKE pe.generic_name
      OR (pe.trade_name IS NOT NULL AND m.canonical_name ILIKE pe.trade_name)
    WHERE pe.approval_date IS NOT NULL
),

-- ── Source 2b: Orange/Purple Book exclusivity expiry dates ───────────────────
ob_exclusivity_events AS (
    SELECT DISTINCT ON (m.molecule_id, pe.application_number, pe.exclusivity_code)
        m.molecule_id,
        'FDA'                                                                  AS agency,
        COALESCE(pe.trade_name, pe.generic_name)                              AS drug_name,
        pe.generic_name                                                        AS active_substance,
        NULL::TEXT                                                             AS indication,
        'exclusivity_' || pe.exclusivity_code                                 AS decision,
        pe.exclusivity_date                                                    AS decision_date,
        NULL::TEXT                                                             AS therapeutic_area,
        pe.exclusivity_code                                                    AS recommendation,
        pe.application_number || '-excl-' || pe.exclusivity_code             AS decision_id,
        pe.product_number,
        COALESCE(pe.trade_name, pe.generic_name)                              AS product_name,
        pe.generic_name                                                        AS inn,
        NULL::TEXT                                                             AS atc_code,
        pe.applicant                                                           AS marketing_authorization_holder,
        NULL::TEXT                                                             AS authorization_status,
        NULL::DATE                                                             AS authorization_date,
        NULL::TEXT                                                             AS epar_url,
        NULL::TEXT                                                             AS guidance_id,
        NULL::TEXT                                                             AS title,
        NULL::TEXT                                                             AS url,
        NULL::NUMERIC                                                          AS icer_value
    FROM mol_silver.patent_exclusivities pe
    JOIN mol_silver.molecules m
      ON m.canonical_name ILIKE pe.generic_name
      OR (pe.trade_name IS NOT NULL AND m.canonical_name ILIKE pe.trade_name)
    WHERE pe.exclusivity_date IS NOT NULL
      AND pe.exclusivity_code IS NOT NULL
),

-- ── Source 3: EMA authorization dates (name-joined) ─────────────────────────
ema_events AS (
    SELECT DISTINCT ON (m.molecule_id, er.product_number)
        m.molecule_id,
        'EMA'                                                                  AS agency,
        COALESCE(er.product_name, er.active_substance)                        AS drug_name,
        er.active_substance                                                    AS active_substance,
        NULL::TEXT                                                             AS indication,
        'EMA_authorization'                                                    AS decision,
        er.authorization_date                                                  AS decision_date,
        er.therapeutic_area,
        er.authorization_status                                                AS recommendation,
        er.product_number                                                      AS decision_id,
        er.product_number,
        er.product_name,
        er.inn,
        er.atc_code,
        er.marketing_authorization_holder,
        er.authorization_status,
        er.authorization_date,
        er.epar_url,
        NULL::TEXT                                                             AS guidance_id,
        NULL::TEXT                                                             AS title,
        NULL::TEXT                                                             AS url,
        NULL::NUMERIC                                                          AS icer_value
    FROM mol_silver.ema_regulatory er
    JOIN mol_silver.molecules m
      ON m.canonical_name ILIKE er.active_substance
      OR (er.inn IS NOT NULL AND m.canonical_name ILIKE er.inn)
    WHERE er.authorization_date IS NOT NULL
),

all_events AS (
    SELECT * FROM fda_label_events
    UNION ALL
    SELECT * FROM ob_approval_events
    UNION ALL
    SELECT * FROM ob_exclusivity_events
    UNION ALL
    SELECT * FROM ema_events
)

SELECT
    gen_random_uuid()            AS id,
    molecule_id,
    agency,
    drug_name,
    active_substance,
    indication,
    decision,
    decision_date,
    therapeutic_area,
    recommendation,
    product_number,
    product_name,
    inn,
    atc_code,
    marketing_authorization_holder,
    authorization_status,
    authorization_date,
    epar_url,
    guidance_id,
    title,
    url,
    icer_value,
    decision_id,
    NOW()                        AS created_at,
    NOW()                        AS updated_at
FROM all_events
WHERE molecule_id IS NOT NULL
  AND decision_id IS NOT NULL;

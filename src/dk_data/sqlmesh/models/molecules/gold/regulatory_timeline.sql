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

WITH regulatory AS (
    SELECT
        rd.agency,
        -- Use actual bronze column names; COALESCE across EMA/HTA sources
        COALESCE(rd.drug_name, rd.product_name) AS drug_name,
        rd.active_substance,
        rd.indication,
        COALESCE(rd.decision, rd.authorization_status) AS decision,
        COALESCE(rd.decision_date, rd.authorization_date) AS decision_date,
        rd.therapeutic_area,
        rd.recommendation,
        -- EMA-specific (carried through from bronze)
        rd.product_number,
        rd.product_name,
        rd.inn,
        rd.atc_code,
        rd.marketing_authorization_holder,
        rd.authorization_status,
        rd.authorization_date,
        rd.epar_url,
        -- HTA-specific (carried through from bronze)
        rd.guidance_id,
        rd.title,
        rd.url,
        rd.icer_value,
        rd.decision_id
    FROM mol_silver.regulatory_decisions rd
),

-- Join with molecules to get molecule_id
molecule_linked AS (
    SELECT
        m.molecule_id,
        r.*
    FROM regulatory r
    LEFT JOIN mol_silver.molecules_from_bronze m
        ON LOWER(r.drug_name) = LOWER(m.pref_name)
        OR LOWER(r.active_substance) = LOWER(m.pref_name)
)

SELECT DISTINCT ON (molecule_id, agency, decision_id)
    gen_random_uuid() AS id,
    molecule_id,
    agency,
    drug_name,
    active_substance,
    indication,
    decision,
    decision_date,
    therapeutic_area,
    recommendation,
    -- EMA columns
    product_number,
    product_name,
    inn,
    atc_code,
    marketing_authorization_holder,
    authorization_status,
    authorization_date,
    epar_url,
    -- HTA columns
    guidance_id,
    title,
    url,
    icer_value,
    decision_id,
    NOW() AS created_at,
    NOW() AS updated_at
FROM molecule_linked
ORDER BY molecule_id, agency, decision_id, decision_date DESC NULLS LAST;

-- SQLMesh Model: Gold Regulatory Timeline
-- Cross-source regulatory decision history per molecule
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_gold.regulatory_timeline,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, agency, decision_date)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (drug_name, agency, decision_date))
    ),
    grain (molecule_id, agency, decision_date)
);

WITH regulatory AS (
    SELECT
        rd.agency,
        rd.drug_name,
        rd.active_substance,
        rd.indication,
        rd.decision,
        rd.decision_date,
        rd.therapeutic_area,
        rd.recommendation_details
    FROM mol_silver.regulatory_decisions rd
),

-- Join with molecules to get molecule_id via drug_name/active_substance matching
molecule_linked AS (
    SELECT
        m.molecule_id,
        r.drug_name,
        r.agency,
        r.active_substance,
        r.indication,
        r.decision,
        r.decision_date,
        r.therapeutic_area,
        r.recommendation_details
    FROM regulatory r
    LEFT JOIN mol_silver.molecules_from_bronze m
        ON LOWER(r.drug_name) = LOWER(m.pref_name)
        OR LOWER(r.active_substance) = LOWER(m.pref_name)
)

SELECT DISTINCT ON (molecule_id, agency, decision_date)
    gen_random_uuid() AS id,
    molecule_id,
    drug_name,
    agency,
    decision,
    decision_date,
    indication,
    recommendation_details,
    NOW() AS created_at,
    NOW() AS updated_at
FROM molecule_linked
ORDER BY molecule_id, agency, decision_date DESC;

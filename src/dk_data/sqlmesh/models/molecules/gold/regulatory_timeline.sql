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

-- mol_silver.regulatory_decisions is populated by ip_silver pipeline (not yet run).
-- Return empty result set with correct schema until ip_silver runs.
SELECT
    gen_random_uuid() AS id,
    NULL::UUID AS molecule_id,
    NULL::TEXT AS agency,
    NULL::TEXT AS drug_name,
    NULL::TEXT AS active_substance,
    NULL::TEXT AS indication,
    NULL::TEXT AS decision,
    NULL::DATE AS decision_date,
    NULL::TEXT AS therapeutic_area,
    NULL::TEXT AS recommendation,
    NULL::TEXT AS product_number,
    NULL::TEXT AS product_name,
    NULL::TEXT AS inn,
    NULL::TEXT AS atc_code,
    NULL::TEXT AS marketing_authorization_holder,
    NULL::TEXT AS authorization_status,
    NULL::DATE AS authorization_date,
    NULL::TEXT AS epar_url,
    NULL::TEXT AS guidance_id,
    NULL::TEXT AS title,
    NULL::TEXT AS url,
    NULL::NUMERIC AS icer_value,
    NULL::TEXT AS decision_id,
    NOW() AS created_at,
    NOW() AS updated_at
WHERE FALSE;

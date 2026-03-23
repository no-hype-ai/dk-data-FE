-- SQLMesh Model: Silver EMA Regulatory
-- Promotes mol_bronze.ema into mol_silver.ema_regulatory with molecule-level linkage.
-- Separate from mol_silver.regulatory_decisions (which combines EMA + HTA decision data).
-- This table exposes EMA authorized medicine details (product, authorization status,
-- approval date, therapeutic area) for EU market context in xenon sections:
--   competitive_positioning, lifecycle_interpretation
-- Entity linking: LEFT JOIN mol_silver.molecules on active_substance name, INN as fallback.
-- FULL refresh ensures molecule_id is always current when new molecules are added.

MODEL (
    name mol_silver.ema_regulatory,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (product_number, active_substance))
    )
);

SELECT
    gen_random_uuid()                       AS ema_regulatory_id,
    COALESCE(m_sub.molecule_id, m_inn.molecule_id) AS molecule_id,
    b.product_number,
    b.product_name,
    b.active_substance,
    b.inn,
    b.atc_code,
    b.marketing_authorization_holder,
    b.authorization_status,
    b.authorization_date,
    b.revision_date,
    b.medicine_type,
    b.therapeutic_area,
    b.pharmacotherapeutic_group,
    b.epar_url,
    b.summary_url,
    'ema'                                   AS source,
    b.ingested_at                           AS created_at

FROM mol_bronze.ema b
LEFT JOIN mol_silver.molecules m_sub
       ON LOWER(m_sub.canonical_name) = LOWER(b.active_substance)
LEFT JOIN mol_silver.molecules m_inn
       ON m_sub.molecule_id IS NULL
      AND b.inn IS NOT NULL
      AND LOWER(m_inn.canonical_name) = LOWER(b.inn)
WHERE b.product_number IS NOT NULL
  AND b.active_substance IS NOT NULL;

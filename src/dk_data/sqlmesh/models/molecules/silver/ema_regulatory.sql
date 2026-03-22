-- SQLMesh Model: Silver EMA Regulatory
-- Promotes mol_bronze.ema into mol_silver.ema_regulatory with molecule-level linkage.
-- Separate from mol_silver.regulatory_decisions (which combines EMA + HTA decision data).
-- This table exposes EMA authorized medicine details (product, authorization status,
-- approval date, therapeutic area) for EU market context in xenon sections:
--   competitive_positioning, lifecycle_interpretation
-- molecule_id is NULL — entity linking fills it via active_substance/inn matching.

MODEL (
    name mol_silver.ema_regulatory,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (product_number)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (product_number, active_substance))
    ),
    grain (product_number)
);

SELECT
    gen_random_uuid()                       AS ema_regulatory_id,
    NULL::UUID                              AS molecule_id,     -- entity linking fills this via active_substance/inn match
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
WHERE b.processed_to_silver = FALSE
  AND b.product_number IS NOT NULL
  AND b.active_substance IS NOT NULL;

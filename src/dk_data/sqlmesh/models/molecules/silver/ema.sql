-- SQLMesh Model: Silver EMA (European Medicines Agency authorised medicines)
-- Promotes mol_bronze.ema to silver, linking to mol_silver.molecules where possible.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Grain: product_number (EMA authorisation number)
-- Source: mol_bronze.ema (from mol_raw.ema via EMAMolFetcher)
-- Note: mol_silver.ema_regulatory covers regulatory decisions (EMARegulatoryCIFetcher);
--       this model covers the EPAR authorized medicines vocabulary.

MODEL (
    name mol_silver.ema,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (product_number, product_name))
    ),
    grain product_number
);

SELECT
    b.product_number,
    b.product_name,
    b.active_substance,
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
    b.inn,
    m.molecule_id,
    b.source,
    b.source_updated_at,
    b.ingested_at                       AS _ingested_at,
    CURRENT_TIMESTAMP                   AS _silver_updated_at
FROM mol_bronze.ema AS b
LEFT JOIN mol_silver.molecules AS m
    ON LOWER(TRIM(b.active_substance)) = LOWER(TRIM(m.canonical_name))
WHERE b.product_number IS NOT NULL
  AND b.product_name IS NOT NULL

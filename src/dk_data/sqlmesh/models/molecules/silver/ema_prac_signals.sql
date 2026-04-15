-- SQLMesh Model: Silver EMA PRAC Signals
-- Extracts pharmacovigilance / safety signal records from mol_bronze.ema
-- by filtering on action_type or document_type containing safety-related keywords.
-- LEFT JOINs to mol_silver.molecules for molecule crosswalk via active_substance.
-- Feature: 006-claims-engine-data-gaps (T030)

MODEL (
    name mol_silver.ema_prac_signals,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (signal_id, drug_name))
    ),
    grain (signal_id)
);

SELECT
    gen_random_uuid()           AS signal_id,
    b.product_name              AS drug_name,
    b.active_substance          AS active_substance,
    -- Derive signal_type from the document/action metadata
    CASE
        WHEN LOWER(COALESCE(b.medicine_type, '')) LIKE '%signal%'
            THEN 'signal_detection'
        WHEN LOWER(COALESCE(b.medicine_type, '')) LIKE '%pharmacovigilance%'
            THEN 'pharmacovigilance_review'
        WHEN LOWER(COALESCE(b.authorization_status, '')) LIKE '%suspend%'
            THEN 'suspension'
        WHEN LOWER(COALESCE(b.authorization_status, '')) LIKE '%withdraw%'
            THEN 'withdrawal'
        ELSE 'safety_review'
    END                         AS signal_type,
    b.revision_date             AS signal_date,
    b.authorization_status      AS outcome,
    b.epar_url                  AS document_url,
    m.id                        AS molecule_id

FROM mol_bronze.ema b
LEFT JOIN mol_silver.molecules m
    ON LOWER(TRIM(b.active_substance)) = LOWER(TRIM(m.name))
WHERE (
    LOWER(COALESCE(b.therapeutic_area, ''))         LIKE '%safety%'
    OR LOWER(COALESCE(b.therapeutic_area, ''))       LIKE '%signal%'
    OR LOWER(COALESCE(b.therapeutic_area, ''))       LIKE '%pharmacovigilance%'
    OR LOWER(COALESCE(b.therapeutic_area, ''))       LIKE '%prac%'
    OR LOWER(COALESCE(b.pharmacotherapeutic_group, '')) LIKE '%safety%'
    OR LOWER(COALESCE(b.pharmacotherapeutic_group, '')) LIKE '%signal%'
    OR LOWER(COALESCE(b.pharmacotherapeutic_group, '')) LIKE '%pharmacovigilance%'
    OR LOWER(COALESCE(b.pharmacotherapeutic_group, '')) LIKE '%prac%'
    OR LOWER(COALESCE(b.medicine_type, ''))          LIKE '%safety%'
    OR LOWER(COALESCE(b.medicine_type, ''))           LIKE '%signal%'
    OR LOWER(COALESCE(b.medicine_type, ''))           LIKE '%pharmacovigilance%'
    OR LOWER(COALESCE(b.medicine_type, ''))           LIKE '%prac%'
    OR LOWER(COALESCE(b.authorization_status, ''))   LIKE '%suspend%'
    OR LOWER(COALESCE(b.authorization_status, ''))   LIKE '%withdraw%'
    OR LOWER(COALESCE(b.authorization_status, ''))   LIKE '%refus%'
);

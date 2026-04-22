-- SQLMesh Model: Silver Device Identifiers
-- Multi-source external-ID crosswalk for the device hub.
-- Source values: k_number, pma_number, pma_supplement, fei_number, udi_di, gudid_key, gmdn_code
-- (today we populate k_number, pma_number, pma_supplement, and fei_number when present).
-- Grain: (source, identifier)

MODEL (
    name dev_silver.device_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (device_id, source, identifier))
    ),
    grain (source, identifier)
);

-- 510(k) k_numbers
SELECT
    ('x' || substr(md5(LOWER(b.k_number)), 1, 16))::bit(64)::bigint AS device_id,
    'k_number'::text                                                 AS source,
    b.k_number                                                       AS identifier,
    TRUE                                                             AS is_primary,
    b.created_at                                                     AS first_seen_at,
    NOW()                                                            AS last_seen_at
FROM dev_bronze.openfda_device_510k b
WHERE b.k_number IS NOT NULL

UNION ALL

-- 510(k) FEI numbers (from openfda.fei_number array) — per-k_number device
SELECT DISTINCT
    ('x' || substr(md5(LOWER(b.k_number)), 1, 16))::bit(64)::bigint AS device_id,
    'fei_number'::text                                               AS source,
    fei.value::text                                                  AS identifier,
    FALSE                                                            AS is_primary,
    b.created_at                                                     AS first_seen_at,
    NOW()                                                            AS last_seen_at
FROM dev_bronze.openfda_device_510k b,
     jsonb_array_elements_text(COALESCE(b.openfda_fei_number, '[]'::jsonb)) AS fei(value)
WHERE b.k_number IS NOT NULL AND fei.value IS NOT NULL

UNION ALL

-- PMA base numbers (supplement '0' or null)
SELECT
    ('x' || substr(md5('pma:' || LOWER(b.pma_number)), 1, 16))::bit(64)::bigint AS device_id,
    'pma_number'::text                                                           AS source,
    b.pma_number                                                                 AS identifier,
    TRUE                                                                         AS is_primary,
    b.created_at                                                                 AS first_seen_at,
    NOW()                                                                        AS last_seen_at
FROM dev_bronze.openfda_device_pma b
WHERE b.pma_number IS NOT NULL
  AND (b.supplement_number = '0' OR b.supplement_number IS NULL)

UNION ALL

-- PMA supplements → pma_supplement source entries, same device_id as base PMA
SELECT
    ('x' || substr(md5('pma:' || LOWER(b.pma_number)), 1, 16))::bit(64)::bigint AS device_id,
    'pma_supplement'::text                                                       AS source,
    b.pma_number || '/' || b.supplement_number                                   AS identifier,
    FALSE                                                                        AS is_primary,
    b.created_at                                                                 AS first_seen_at,
    NOW()                                                                        AS last_seen_at
FROM dev_bronze.openfda_device_pma b
WHERE b.pma_number IS NOT NULL
  AND b.supplement_number IS NOT NULL
  AND b.supplement_number <> '0'

UNION ALL

-- PMA FEI numbers
SELECT DISTINCT
    ('x' || substr(md5('pma:' || LOWER(b.pma_number)), 1, 16))::bit(64)::bigint AS device_id,
    'fei_number'::text                                                           AS source,
    fei.value::text                                                              AS identifier,
    FALSE                                                                        AS is_primary,
    b.created_at                                                                 AS first_seen_at,
    NOW()                                                                        AS last_seen_at
FROM dev_bronze.openfda_device_pma b,
     jsonb_array_elements_text(COALESCE(b.openfda_fei_number, '[]'::jsonb)) AS fei(value)
WHERE b.pma_number IS NOT NULL AND fei.value IS NOT NULL;

-- SQLMesh Model: Silver Devices Hub
-- Populates dev_silver.devices (hub table, created in migration 250) from
-- dev_bronze.openfda_device_{510k,pma} union. One row per canonical device.
--
-- device_id = deterministic bigint hash per Rule P2 priority:
--   UDI-DI → k_number → pma_number → fei_number → normalized_name
-- Today UDI-DI and FEI are absent from input; priority degrades to k_number
-- (510k path) or pma_number (PMA path).
--
-- Hub IDs are IMMUTABLE (P1) — ON CONFLICT DO UPDATE only refreshes data_sources
-- and last_seen_at, never recomputes device_id.
--
-- Grain: device_id

MODEL (
    name dev_silver.devices,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key device_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (device_id, canonical_name, primary_source))
    ),
    grain device_id
);

WITH sources AS (
    -- 510(k) path: device_id = md5(lower(k_number))
    SELECT
        ('x' || substr(md5(LOWER(b.k_number)), 1, 16))::bit(64)::bigint AS device_id,
        b.device_name                                                    AS canonical_name,
        b.k_number                                                       AS primary_identifier,
        'k_number'::text                                                 AS primary_source,
        b.product_code,
        b.openfda_device_class                                           AS device_class,
        b.openfda_regulation_number                                      AS regulation_number,
        'openfda_device_510k'::text                                      AS source_name,
        b.created_at
    FROM dev_bronze.openfda_device_510k b
    WHERE b.k_number IS NOT NULL AND b.device_name IS NOT NULL

    UNION ALL

    -- PMA path: device_id = md5('pma:' || lower(pma_number)) — supplements
    -- collapse onto the base PMA's device_id (we do NOT include supplement_number
    -- in the hash so device supplements land on the same hub row).
    SELECT
        ('x' || substr(md5('pma:' || LOWER(b.pma_number)), 1, 16))::bit(64)::bigint AS device_id,
        COALESCE(b.trade_name, b.device_name, b.generic_name)            AS canonical_name,
        b.pma_number                                                     AS primary_identifier,
        'pma_number'::text                                               AS primary_source,
        b.product_code,
        b.openfda_device_class                                           AS device_class,
        b.openfda_regulation_number                                      AS regulation_number,
        'openfda_device_pma'::text                                       AS source_name,
        b.created_at
    FROM dev_bronze.openfda_device_pma b
    WHERE b.pma_number IS NOT NULL
      AND (b.supplement_number = '0' OR b.supplement_number IS NULL)  -- base PMA only for hub row
      AND COALESCE(b.trade_name, b.device_name, b.generic_name) IS NOT NULL
)
SELECT DISTINCT ON (device_id)
    device_id,
    canonical_name,
    primary_identifier,
    primary_source,
    product_code,
    device_class,
    regulation_number,
    NULL::BOOLEAN                                                        AS is_implant,              -- populated by fda_classification join at query time
    NULL::BOOLEAN                                                        AS is_life_sustaining,
    NULL::BOOLEAN                                                        AS is_drug_delivery_combo,  -- TODO: classify via product_code lookup
    jsonb_build_array(source_name)                                       AS data_sources,
    MIN(created_at) OVER (PARTITION BY device_id)                        AS first_seen_at,
    NOW()                                                                AS last_seen_at,
    NOW()                                                                AS created_at,
    NOW()                                                                AS updated_at
FROM sources
ORDER BY device_id, primary_source;   -- deterministic tiebreak

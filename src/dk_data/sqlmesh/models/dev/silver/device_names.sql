-- SQLMesh Model: Silver Device Names
-- Canonical + alias names per device with normalized_name for trigram fuzzy resolve.
-- normalized_name = LOWER(TRIM(regexp_replace(name, '\s+', ' ', 'g'))) — aggressive
-- canonicalization per Rule H2 to avoid biologic-style split-brain (audit §5.4).
-- Grain: (normalized_name, device_id, source)

MODEL (
    name dev_silver.device_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, device_id, source)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (device_id, normalized_name, display_name))
    ),
    grain (normalized_name, device_id, source)
);

-- 510(k) canonical device_name
SELECT
    ('x' || substr(md5(LOWER(b.k_number)), 1, 16))::bit(64)::bigint AS device_id,
    LOWER(TRIM(regexp_replace(b.device_name, '\s+', ' ', 'g')))      AS normalized_name,
    b.device_name                                                    AS display_name,
    'canonical'::text                                                AS name_kind,
    'openfda_device_510k'::text                                      AS source,
    b.created_at                                                     AS first_seen_at
FROM dev_bronze.openfda_device_510k b
WHERE b.k_number IS NOT NULL
  AND b.device_name IS NOT NULL
  AND LENGTH(TRIM(b.device_name)) >= 4

UNION ALL

-- 510(k) openfda_device_name as alias
SELECT
    ('x' || substr(md5(LOWER(b.k_number)), 1, 16))::bit(64)::bigint AS device_id,
    LOWER(TRIM(regexp_replace(b.openfda_device_name, '\s+', ' ', 'g'))) AS normalized_name,
    b.openfda_device_name                                            AS display_name,
    'alias'::text                                                    AS name_kind,
    'openfda_device_510k'::text                                      AS source,
    b.created_at                                                     AS first_seen_at
FROM dev_bronze.openfda_device_510k b
WHERE b.k_number IS NOT NULL
  AND b.openfda_device_name IS NOT NULL
  AND LENGTH(TRIM(b.openfda_device_name)) >= 4
  AND LOWER(TRIM(regexp_replace(b.openfda_device_name, '\s+', ' ', 'g')))
    <> LOWER(TRIM(regexp_replace(b.device_name, '\s+', ' ', 'g')))

UNION ALL

-- PMA canonical (trade_name → device_name → generic_name)
SELECT
    ('x' || substr(md5('pma:' || LOWER(b.pma_number)), 1, 16))::bit(64)::bigint AS device_id,
    LOWER(TRIM(regexp_replace(
        COALESCE(b.trade_name, b.device_name, b.generic_name), '\s+', ' ', 'g'
    )))                                                                          AS normalized_name,
    COALESCE(b.trade_name, b.device_name, b.generic_name)                        AS display_name,
    CASE WHEN b.trade_name IS NOT NULL THEN 'trade' ELSE 'canonical' END         AS name_kind,
    'openfda_device_pma'::text                                                   AS source,
    b.created_at                                                                 AS first_seen_at
FROM dev_bronze.openfda_device_pma b
WHERE b.pma_number IS NOT NULL
  AND COALESCE(b.trade_name, b.device_name, b.generic_name) IS NOT NULL
  AND LENGTH(TRIM(COALESCE(b.trade_name, b.device_name, b.generic_name))) >= 4

UNION ALL

-- PMA generic_name as additional alias (when trade_name was canonical)
SELECT
    ('x' || substr(md5('pma:' || LOWER(b.pma_number)), 1, 16))::bit(64)::bigint AS device_id,
    LOWER(TRIM(regexp_replace(b.generic_name, '\s+', ' ', 'g')))                 AS normalized_name,
    b.generic_name                                                               AS display_name,
    'generic'::text                                                              AS name_kind,
    'openfda_device_pma'::text                                                   AS source,
    b.created_at                                                                 AS first_seen_at
FROM dev_bronze.openfda_device_pma b
WHERE b.pma_number IS NOT NULL
  AND b.generic_name IS NOT NULL
  AND b.trade_name IS NOT NULL  -- only emit generic as alias when trade is canonical
  AND LENGTH(TRIM(b.generic_name)) >= 4
  AND LOWER(TRIM(regexp_replace(b.generic_name, '\s+', ' ', 'g')))
    <> LOWER(TRIM(regexp_replace(b.trade_name, '\s+', ' ', 'g')));

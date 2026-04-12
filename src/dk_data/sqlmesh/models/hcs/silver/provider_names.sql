-- T038: hcs_silver.provider_names — provider name index
-- Full name variants (last, first, middle, credential) for fuzzy resolution.

MODEL (
    name hcs_silver.provider_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, provider_id, source)
    ),
    grain (normalized_name, provider_id, source)
);

WITH pecos_names AS (
    SELECT
        LOWER(TRIM(last_name || ', ' || first_name || COALESCE(' ' || middle_name, ''))) AS normalized_name,
        ('x' || substr(md5(COALESCE(npi, 'pecos:' || pecos_id)), 1, 16))::bit(64)::bigint AS provider_id,
        'canonical'                                                              AS name_kind,
        'pecos'                                                                  AS source,
        1.0                                                                      AS confidence,
        last_name || ', ' || first_name || COALESCE(' ' || middle_name, '')     AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pecos
    WHERE last_name IS NOT NULL
      AND first_name IS NOT NULL
      AND COALESCE(npi, pecos_id) IS NOT NULL
),

npi_names AS (
    SELECT
        LOWER(TRIM(provider_last_name_legal_name || ', ' || provider_first_name)) AS normalized_name,
        ('x' || substr(md5(npi), 1, 16))::bit(64)::bigint                      AS provider_id,
        'canonical'                                                              AS name_kind,
        'npi_registry'                                                           AS source,
        1.0                                                                      AS confidence,
        provider_last_name_legal_name || ', ' || provider_first_name            AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_npi
    WHERE npi IS NOT NULL
      AND entity_type_code = '1'
      AND provider_last_name_legal_name IS NOT NULL
      AND provider_first_name IS NOT NULL
),

all_names AS (
    SELECT * FROM pecos_names
    UNION ALL
    SELECT * FROM npi_names
)

SELECT DISTINCT ON (normalized_name, provider_id, source)
    normalized_name,
    provider_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND provider_id IS NOT NULL
ORDER BY normalized_name, provider_id, source, first_seen_at ASC;

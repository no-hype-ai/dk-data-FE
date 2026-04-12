-- T038: hcs_silver.provider_identifiers — provider identifier crosswalk
-- Covers: npi, pecos_id, dea_number, state_license.

MODEL (
    name hcs_silver.provider_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier)
);

WITH pecos_ids AS (
    SELECT
        'npi'                                                                    AS source,
        npi                                                                      AS identifier,
        ('x' || substr(md5(COALESCE(npi, 'pecos:' || pecos_id)), 1, 16))::bit(64)::bigint AS provider_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pecos
    WHERE npi IS NOT NULL

    UNION ALL

    SELECT
        'pecos_id'                                                               AS source,
        pecos_id                                                                 AS identifier,
        ('x' || substr(md5(COALESCE(npi, 'pecos:' || pecos_id)), 1, 16))::bit(64)::bigint AS provider_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pecos
    WHERE pecos_id IS NOT NULL
),

npi_ids AS (
    SELECT
        'npi'                                                                    AS source,
        npi                                                                      AS identifier,
        ('x' || substr(md5(npi), 1, 16))::bit(64)::bigint                      AS provider_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_npi
    WHERE npi IS NOT NULL
      AND entity_type_code = '1'
),

all_ids AS (
    SELECT * FROM pecos_ids
    UNION ALL
    SELECT * FROM npi_ids
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    provider_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_ids
WHERE provider_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS hcs_silver_prov_ident_src_id_idx ON hcs_silver.provider_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS hcs_silver_prov_ident_prov_idx ON hcs_silver.provider_identifiers (provider_id);

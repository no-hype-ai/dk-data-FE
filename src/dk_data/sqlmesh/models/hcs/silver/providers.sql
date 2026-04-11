-- T038: hcs_silver.providers — healthcare provider hub
-- Hub architecture: one row per unique provider, keyed by NPI (primary) or PECOS ID.
-- Columns: provider_id, npi, pecos_id, first_name, last_name, middle_name,
--          credential, primary_taxonomy_code, primary_specialty, state,
--          first_seen_at, last_updated_at.

MODEL (
    name hcs_silver.providers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key provider_id
    ),
    grain provider_id
);

WITH npi_providers AS (
    SELECT
        ('x' || substr(md5(COALESCE(npi, 'pecos:' || pecos_id)), 1, 16))::bit(64)::bigint AS provider_id,
        NULLIF(npi, '')                                                          AS npi,
        NULLIF(pecos_id, '')                                                     AS pecos_id,
        NULLIF(first_name, '')                                                   AS first_name,
        NULLIF(last_name, '')                                                    AS last_name,
        NULLIF(middle_name, '')                                                  AS middle_name,
        NULLIF(credential, '')                                                   AS credential,
        NULLIF(primary_taxonomy_code, '')                                        AS primary_taxonomy_code,
        NULLIF(primary_specialty, '')                                            AS primary_specialty,
        NULLIF(state, '')                                                        AS state,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pecos
    WHERE COALESCE(npi, pecos_id) IS NOT NULL
),

npi_registry AS (
    SELECT
        ('x' || substr(md5(npi), 1, 16))::bit(64)::bigint                      AS provider_id,
        npi,
        NULL::text                                                               AS pecos_id,
        first_name,
        last_name,
        middle_name,
        credential,
        primary_taxonomy_code,
        primary_specialty,
        mailing_address_state                                                    AS state,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_npi
    WHERE npi IS NOT NULL
      AND entity_type_code = '1'  -- individuals only
),

all_providers AS (
    SELECT * FROM npi_providers
    UNION ALL
    SELECT * FROM npi_registry
),

deduped AS (
    SELECT DISTINCT ON (provider_id)
        provider_id,
        npi,
        pecos_id,
        first_name,
        last_name,
        middle_name,
        credential,
        primary_taxonomy_code,
        primary_specialty,
        state,
        first_seen_at
    FROM all_providers
    ORDER BY provider_id, src_priority ASC
)

SELECT
    provider_id,
    npi,
    pecos_id,
    first_name,
    last_name,
    middle_name,
    credential,
    primary_taxonomy_code,
    primary_specialty,
    state,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- CREATE INDEX IF NOT EXISTS hcs_silver_prov_name_idx ON hcs_silver.providers (last_name, first_name, state);

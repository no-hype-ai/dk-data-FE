-- T039: hcs_silver.facility_identifiers — facility identifier crosswalk
-- Covers: ccn, npi_type2, ncdr_id, cms_certification_number.

MODEL (
    name hcs_silver.facility_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH pos_ids AS (
    SELECT
        'ccn'                                                                    AS source,
        provider_transaction_access_number                                       AS identifier,
        ('x' || substr(md5(COALESCE(provider_transaction_access_number, npi, facility_name)), 1, 16))::bit(64)::bigint AS facility_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pos
    WHERE provider_transaction_access_number IS NOT NULL

    UNION ALL

    SELECT
        'npi_type2'                                                              AS source,
        npi                                                                      AS identifier,
        ('x' || substr(md5(COALESCE(provider_transaction_access_number, npi, facility_name)), 1, 16))::bit(64)::bigint AS facility_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pos
    WHERE npi IS NOT NULL
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    facility_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM pos_ids
WHERE facility_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS hcs_silver_fac_ident_src_id_idx ON hcs_silver.facility_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS hcs_silver_fac_ident_fac_idx ON hcs_silver.facility_identifiers (facility_id);

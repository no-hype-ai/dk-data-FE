-- T042: ip_silver.design_identifiers — design identifier crosswalk

MODEL (
    name ip_silver.design_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier)
);

WITH euipo_ids AS (
    SELECT
        'eu_design'                                                              AS source,
        design_number                                                            AS identifier,
        ('x' || substr(md5('EU:' || COALESCE(design_number, application_number)), 1, 16))::bit(64)::bigint AS design_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.euipo_designs
    WHERE design_number IS NOT NULL

    UNION ALL

    SELECT
        'eu_application'                                                         AS source,
        application_number                                                       AS identifier,
        ('x' || substr(md5('EU:' || COALESCE(design_number, application_number)), 1, 16))::bit(64)::bigint AS design_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.euipo_designs
    WHERE application_number IS NOT NULL
      AND design_number IS NULL
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    design_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM euipo_ids
WHERE design_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

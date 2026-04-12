-- T041: ip_silver.trademark_identifiers — trademark identifier crosswalk

MODEL (
    name ip_silver.trademark_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH uspto_ids AS (
    SELECT
        'us_registration'                                                        AS source,
        registration_number                                                      AS identifier,
        ('x' || substr(md5('US:' || COALESCE(registration_number, serial_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_trademarks
    WHERE registration_number IS NOT NULL

    UNION ALL

    SELECT
        'us_serial'                                                              AS source,
        serial_number                                                            AS identifier,
        ('x' || substr(md5('US:' || COALESCE(registration_number, serial_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_trademarks
    WHERE serial_number IS NOT NULL
),

euipo_ids AS (
    SELECT
        'eu_registration'                                                        AS source,
        registration_number                                                      AS identifier,
        ('x' || substr(md5('EU:' || COALESCE(registration_number, application_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.euipo_trademarks
    WHERE registration_number IS NOT NULL
),

all_ids AS (
    SELECT * FROM uspto_ids
    UNION ALL
    SELECT * FROM euipo_ids
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    trademark_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_ids
WHERE trademark_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- T041: ip_silver.trademarks — trademark hub (NEW)
-- Hub architecture: one row per unique trademark keyed by (jurisdiction, registration_number).
-- Sources: USPTO trademarks, EUIPO trademarks from bronze.

MODEL (
    name ip_silver.trademarks,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key trademark_id
    ),
    grain trademark_id
);

WITH uspto_trademarks AS (
    SELECT
        ('x' || substr(md5('US:' || COALESCE(registration_number, serial_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        'US'                                                                     AS jurisdiction,
        NULLIF(registration_number, '')                                          AS registration_number,
        NULLIF(serial_number, '')                                                AS serial_number,
        NULL::text                                                               AS wipo_madrid_number,
        NULLIF(mark_text, '')                                                    AS mark_text,
        NULLIF(mark_type, '')                                                    AS mark_type,
        nice_classes,
        registration_date::date                                                  AS registration_date,
        expiry_date::date                                                        AS expiry_date,
        NULLIF(status, '')                                                       AS status,
        NULL::bigint                                                             AS owner_company_id,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_trademarks
    WHERE COALESCE(registration_number, serial_number) IS NOT NULL
      AND mark_text IS NOT NULL
),

euipo_trademarks AS (
    SELECT
        ('x' || substr(md5('EU:' || COALESCE(registration_number, application_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        'EU'                                                                     AS jurisdiction,
        NULLIF(registration_number, '')                                          AS registration_number,
        NULLIF(application_number, '')                                           AS serial_number,
        NULL::text                                                               AS wipo_madrid_number,
        NULLIF(mark_text, '')                                                    AS mark_text,
        NULLIF(mark_type, '')                                                    AS mark_type,
        nice_classes,
        registration_date::date                                                  AS registration_date,
        expiry_date::date                                                        AS expiry_date,
        NULLIF(status, '')                                                       AS status,
        NULL::bigint                                                             AS owner_company_id,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.euipo_trademarks
    WHERE COALESCE(registration_number, application_number) IS NOT NULL
      AND mark_text IS NOT NULL
),

all_trademarks AS (
    SELECT * FROM uspto_trademarks
    UNION ALL
    SELECT * FROM euipo_trademarks
),

deduped AS (
    SELECT DISTINCT ON (trademark_id)
        trademark_id,
        jurisdiction,
        registration_number,
        serial_number,
        wipo_madrid_number,
        mark_text,
        mark_type,
        nice_classes,
        registration_date,
        expiry_date,
        status,
        owner_company_id,
        first_seen_at
    FROM all_trademarks
    ORDER BY trademark_id, src_priority ASC
)

SELECT
    trademark_id,
    jurisdiction,
    registration_number,
    serial_number,
    wipo_madrid_number,
    mark_text,
    mark_type,
    nice_classes,
    registration_date,
    expiry_date,
    status,
    owner_company_id,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- CREATE INDEX IF NOT EXISTS ip_silver_tm_mark_text_idx ON ip_silver.trademarks (mark_text);
-- CREATE INDEX IF NOT EXISTS ip_silver_tm_gin_mark_idx ON ip_silver.trademarks USING GIN (LOWER(mark_text) gin_trgm_ops);
-- CREATE INDEX IF NOT EXISTS ip_silver_tm_gin_classes_idx ON ip_silver.trademarks USING GIN (nice_classes);
-- CREATE INDEX IF NOT EXISTS ip_silver_tm_owner_idx ON ip_silver.trademarks (owner_company_id);

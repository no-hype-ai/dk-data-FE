-- T041: ip_silver.trademark_names — trademark name / mark text index

MODEL (
    name ip_silver.trademark_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, trademark_id, source)
    ),
    grain (normalized_name, trademark_id, source)
);

WITH uspto_marks AS (
    SELECT
        LOWER(TRIM(mark_text))                                                   AS normalized_name,
        ('x' || substr(md5('US:' || COALESCE(registration_number, serial_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        'mark_text'                                                              AS name_kind,
        'uspto'                                                                  AS source,
        1.0                                                                      AS confidence,
        mark_text                                                                AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_trademarks
    WHERE mark_text IS NOT NULL
      AND COALESCE(registration_number, serial_number) IS NOT NULL
),

euipo_marks AS (
    SELECT
        LOWER(TRIM(mark_text))                                                   AS normalized_name,
        ('x' || substr(md5('EU:' || COALESCE(registration_number, application_number)), 1, 16))::bit(64)::bigint AS trademark_id,
        'mark_text'                                                              AS name_kind,
        'euipo'                                                                  AS source,
        1.0                                                                      AS confidence,
        mark_text                                                                AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.euipo_trademarks
    WHERE mark_text IS NOT NULL
      AND COALESCE(registration_number, application_number) IS NOT NULL
),

all_names AS (
    SELECT * FROM uspto_marks
    UNION ALL
    SELECT * FROM euipo_marks
)

SELECT DISTINCT ON (normalized_name, trademark_id, source)
    normalized_name,
    trademark_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND trademark_id IS NOT NULL
ORDER BY normalized_name, trademark_id, source, first_seen_at ASC;

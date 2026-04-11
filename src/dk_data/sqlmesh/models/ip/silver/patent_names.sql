-- T040: ip_silver.patent_names — patent title / name index
-- Normalized titles for fuzzy resolution.

MODEL (
    name ip_silver.patent_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, patent_id, source)
    ),
    grain (normalized_name, patent_id, source)
);

WITH uspto_titles AS (
    SELECT
        LOWER(TRIM(title))                                                       AS normalized_name,
        ('x' || substr(md5('US:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        'title'                                                                  AS name_kind,
        'uspto'                                                                  AS source,
        1.0                                                                      AS confidence,
        title                                                                    AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_patents
    WHERE title IS NOT NULL
      AND COALESCE(patent_number, application_number, publication_number) IS NOT NULL
),

epo_titles AS (
    SELECT
        LOWER(TRIM(title))                                                       AS normalized_name,
        ('x' || substr(md5('EP:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        'title'                                                                  AS name_kind,
        'epo'                                                                    AS source,
        1.0                                                                      AS confidence,
        title                                                                    AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.epo_patents
    WHERE title IS NOT NULL
      AND COALESCE(patent_number, application_number, publication_number) IS NOT NULL
),

all_names AS (
    SELECT * FROM uspto_titles
    UNION ALL
    SELECT * FROM epo_titles
)

SELECT DISTINCT ON (normalized_name, patent_id, source)
    normalized_name,
    patent_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND patent_id IS NOT NULL
ORDER BY normalized_name, patent_id, source, first_seen_at ASC;

-- CREATE INDEX IF NOT EXISTS ip_silver_pat_names_pat_idx ON ip_silver.patent_names (patent_id);
-- CREATE INDEX IF NOT EXISTS ip_silver_pat_names_gin_idx ON ip_silver.patent_names USING GIN (normalized_name gin_trgm_ops);

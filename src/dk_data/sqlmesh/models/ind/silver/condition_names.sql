-- T036: ind_silver.condition_names — condition name index
-- Canonical name, synonyms, lay terms from ICD and MeSH sources.

MODEL (
    name ind_silver.condition_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, condition_id, source)
    ),
    grain (normalized_name, condition_id, source)
);

WITH icd_names AS (
    SELECT
        LOWER(TRIM(COALESCE(condition_name, label, icd10_code)))                AS normalized_name,
        ('x' || substr(md5(COALESCE(icd11_code, icd10_code, mesh_id, meddra_pt, LOWER(condition_name))), 1, 16))::bit(64)::bigint AS condition_id,
        'canonical'                                                              AS name_kind,
        'icd'                                                                    AS source,
        1.0                                                                      AS confidence,
        COALESCE(condition_name, label, icd10_code)                              AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd_codes
    WHERE COALESCE(condition_name, label) IS NOT NULL
),

icd11_names AS (
    SELECT
        LOWER(TRIM(COALESCE(title, code)))                                       AS normalized_name,
        ('x' || substr(md5(code), 1, 16))::bit(64)::bigint                     AS condition_id,
        'canonical'                                                              AS name_kind,
        'icd11'                                                                  AS source,
        1.0                                                                      AS confidence,
        COALESCE(title, code)                                                    AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd11_codes
    WHERE COALESCE(title, code) IS NOT NULL
),

all_names AS (
    SELECT * FROM icd_names
    UNION ALL
    SELECT * FROM icd11_names
)

SELECT DISTINCT ON (normalized_name, condition_id, source)
    normalized_name,
    condition_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND condition_id IS NOT NULL
ORDER BY normalized_name, condition_id, source, first_seen_at ASC;

-- CREATE INDEX IF NOT EXISTS ind_silver_cond_names_cond_idx ON ind_silver.condition_names (condition_id);
-- CREATE INDEX IF NOT EXISTS ind_silver_cond_names_gin_idx ON ind_silver.condition_names USING GIN (normalized_name gin_trgm_ops);

-- SQLMesh Model: Silver ICD Codes
-- Normalized WHO ICD-10 classification codes
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name silver.icd_codes,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key icd_code
    ),
    cron '@monthly',
    audits (
        not_null(columns := (icd_code, title)),
        unique_values(columns := (icd_code))
    ),
    grain icd_code
);

SELECT
    gen_random_uuid() AS id,
    icd_code,
    title,
    chapter,
    block_id,
    category,
    -- Derive parent code from ICD hierarchy (e.g., C34.1 -> C34)
    CASE
        WHEN icd_code LIKE '%.%' THEN split_part(icd_code, '.', 1)
        WHEN length(icd_code) > 3 THEN left(icd_code, 3)
        ELSE NULL
    END AS parent_code,
    -- Leaf codes have no children (codes with decimal points are typically leaf)
    CASE
        WHEN icd_code LIKE '%.%' THEN TRUE
        ELSE FALSE
    END AS is_leaf,
    includes::TEXT AS includes_text,
    excludes::TEXT AS excludes_text,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM bronze.who_icd
WHERE processed_to_silver = FALSE
  AND icd_code IS NOT NULL;

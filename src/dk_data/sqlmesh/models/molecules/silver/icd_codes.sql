-- SQLMesh Model: Silver ICD Codes
-- Normalized WHO ICD-10 / ICD-11 classification codes.
--
-- Reads from mol_bronze.who_icd which provides:
--   icd_code TEXT            -- ICD code (e.g. "C34.1" or "1C83.0")
--   title TEXT               -- human-readable title (extracted from @value or description)
--   class_kind TEXT          -- 'category' | 'block' | 'chapter' (ICD-11 only)
--   browser_url TEXT         -- canonical WHO browser URL
--   definition TEXT          -- definition text
--   parent_uris JSONB        -- array of parent @id URIs (ICD-11)
--   child_uris JSONB         -- array of child @id URIs (ICD-11)
--   inclusion_terms JSONB    -- inclusion terms array
--   exclusion_terms JSONB    -- exclusion terms (excludes1 / exclusion)
--   exclusion_terms2 JSONB   -- additional exclusions (excludes2, ICD-10 only)
--
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_silver.icd_codes,
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
    gen_random_uuid()                                    AS id,
    icd_code::TEXT                                       AS icd_code,
    title::TEXT                                          AS title,
    class_kind::TEXT                                     AS class_kind,
    browser_url::TEXT                                    AS browser_url,
    definition::TEXT                                     AS definition,

    -- Derive parent code from ICD hierarchy.
    -- ICD-10 codes follow a predictable string pattern:
    --   "A00.0" (4-char leaf)   -> parent "A00"  (split on '.')
    --   "A00"   (3-char)        -> parent NULL    (block parent is non-code range like "A00-A09")
    -- ICD-11 codes do NOT follow a predictable string hierarchy; their parent entity IDs
    -- are in parent_uris as full WHO API URIs. We extract the parent code via a
    -- self-join below where possible; otherwise NULL.
    -- String truncation (left(code,3)) is intentionally avoided for ICD-11 — it produces
    -- non-existent codes (e.g. "1A0" from "1A00").
    CASE
        WHEN icd_code LIKE '%.%'
            -- ICD-10 leaf: "A00.0" -> "A00"
            THEN split_part(icd_code, '.', 1)
        WHEN icd_code ~ '^[A-Z][0-9]{2}$'
            -- ICD-10 3-char code: no string-derivable parent (parent is a block range)
            THEN NULL
        ELSE NULL
    END                                                  AS parent_code,

    -- Leaf codes have sub-decimal specificity (ICD-10 pattern)
    -- ICD-11 uses class_kind='category' for leaf-level codes
    CASE
        WHEN icd_code LIKE '%.%'      THEN TRUE
        WHEN class_kind = 'category'  THEN TRUE
        ELSE FALSE
    END                                                  AS is_leaf,

    -- Parent/child URI arrays kept as JSONB for hierarchy traversal
    parent_uris                                          AS parent_uris,
    child_uris                                           AS child_uris,

    -- Inclusion terms as a flat text summary for search/display
    CASE
        WHEN inclusion_terms IS NOT NULL
            THEN inclusion_terms::TEXT
        ELSE NULL
    END                                                  AS includes_text,

    -- Exclusion terms as a flat text summary
    CASE
        WHEN exclusion_terms IS NOT NULL OR exclusion_terms2 IS NOT NULL
            THEN COALESCE(exclusion_terms::TEXT, '') ||
                 CASE WHEN exclusion_terms2 IS NOT NULL
                      THEN ' ' || exclusion_terms2::TEXT
                      ELSE ''
                 END
        ELSE NULL
    END                                                  AS excludes_text,

    -- Coding hints (ICD-10 only): mandatory additional-code instructions on some chapters/blocks
    coding_hint                                          AS coding_hint,

    source::TEXT                                         AS source,
    source_updated_at::TIMESTAMPTZ                       AS source_updated_at,
    NOW()                                                AS created_at,
    NOW()                                                AS updated_at

FROM mol_bronze.who_icd
WHERE
    processed_to_silver = FALSE
    AND icd_code IS NOT NULL
    AND title IS NOT NULL;

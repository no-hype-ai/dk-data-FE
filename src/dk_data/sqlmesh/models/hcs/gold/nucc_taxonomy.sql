-- SQLMesh Model: Gold NUCC Taxonomy Reference
-- Denormalized NUCC provider taxonomy for API consumption and downstream joins.
-- Adds computed groupings (broad_category) to simplify specialty filtering
-- and a count of CMS providers per taxonomy code (from hcs_silver.provider_profile).
--
-- Key design decisions:
-- 1. grain is taxonomy_code — one row per NUCC code (same as silver)
-- 2. provider_count links back to the actual population using each code — useful for
--    filtering to "active" taxonomy codes (non-zero provider population)
-- 3. broad_category collapses the 90+ NUCC types into 8 analyst-friendly buckets
-- Part of: issue #172 H5

MODEL (
    name hcs_gold.nucc_taxonomy,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (taxonomy_code)),
        unique_values(columns := (taxonomy_code))
    ),
    grain taxonomy_code
);

WITH provider_counts AS (
    SELECT
        taxonomy_code_1                     AS taxonomy_code,
        COUNT(DISTINCT npi)                 AS provider_count
    FROM hcs_silver.provider_profile
    WHERE taxonomy_code_1 IS NOT NULL
    GROUP BY taxonomy_code_1
),

taxonomy_enriched AS (
    SELECT
        t.taxonomy_code,
        t.type,
        t.classification,
        t.specialization,

        -- Broad category for simplified filtering
        CASE
            WHEN LOWER(t.type) LIKE '%physician%' OR LOWER(t.classification) LIKE '%physician%'
                THEN 'Physician'
            WHEN LOWER(t.type) LIKE '%nurse%' OR LOWER(t.classification) LIKE '%nurse%'
                THEN 'Nursing'
            WHEN LOWER(t.type) LIKE '%hospital%' OR LOWER(t.type) LIKE '%facility%'
                THEN 'Facility'
            WHEN LOWER(t.type) LIKE '%pharmacy%' OR LOWER(t.classification) LIKE '%pharmacy%'
                THEN 'Pharmacy'
            WHEN LOWER(t.type) LIKE '%dental%' OR LOWER(t.classification) LIKE '%dental%'
                THEN 'Dental'
            WHEN LOWER(t.type) LIKE '%behavioral%' OR LOWER(t.type) LIKE '%mental%'
                THEN 'Behavioral Health'
            WHEN LOWER(t.type) LIKE '%supplier%' OR LOWER(t.type) LIKE '%equipment%'
                THEN 'DME/Supplier'
            ELSE 'Other'
        END                                 AS broad_category,

        COALESCE(pc.provider_count, 0)      AS cms_provider_count,
        pc.provider_count IS NOT NULL       AS has_active_providers
    FROM hcs_silver.ref_nucc_taxonomy t
    LEFT JOIN provider_counts pc ON t.taxonomy_code = pc.taxonomy_code
)

SELECT
    gen_random_uuid()               AS id,
    te.taxonomy_code,
    te.type,
    te.classification,
    te.specialization,
    te.broad_category,
    te.cms_provider_count,
    te.has_active_providers,
    NOW()                           AS gold_built_at

FROM taxonomy_enriched te;

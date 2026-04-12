-- SQLMesh Model: Silver Researchers
-- Normalized researcher profile data from ORCID, enriched with NIH Reporter grant counts.
--
-- Sources:
--   mol_bronze.orcid (mol_bronze.orcid) — ORCID researcher profiles
--   mol_bronze.nih_reporter — NIH grant records with principal_investigators JSONB
--
-- Linkage strategy:
--   NIH grant count is derived by matching nih_reporter.pi_names JSONB array entries
--   (which contain {first_name, last_name}) against ORCID given_name + family_name.
--   This is a best-effort name match; ORCID IDs embedded in NIH data (if present)
--   would allow exact linkage but are not reliably available in the raw API response.
--
-- Fixed (019-cms-puf-platform-reconciliation):
--   - affiliations->0->>'organization-name' → affiliations->0->>'organization'
--     (ORCIDFetcher._parse_employments stores key "organization", not "organization-name")
--   - affiliations->0->>'country' removed — country is not stored in current_affiliations JSONB
--     by the fetcher; replaced with NULL until fetcher is updated to include country
--   - Added NIH Reporter grant_count via LEFT JOIN on PI name match
--   - Model name left as mol_silver.researchers (maps to mol_silver via config.yaml)
--
-- Part of: 015-assessment-dashboard-integration
-- Updated: 019-cms-puf-platform-reconciliation

MODEL (
    name mol_silver.researchers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key orcid_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (orcid_id)),
        unique_values(columns := (orcid_id))
    ),
    grain orcid_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH orcid_base AS (
    SELECT
        gen_random_uuid()                       AS id,
        orcid_id,
        given_name,
        family_name,
        credit_name,
        biography,
        -- Primary affiliation: ORCIDFetcher._parse_employments() stores
        --   {"organization": "...", "role": "...", "department": "..."}
        affiliations->0->>'organization'        AS affiliation,
        -- Full affiliations JSONB array preserved for downstream use
        affiliations,
        -- Country not included in current_affiliations JSONB by the fetcher;
        -- NULL until fetcher is extended to capture address.country
        NULL::TEXT                              AS country,
        works_count,
        -- H-index: not available from ORCID API; populated externally or left NULL
        NULL::INTEGER                           AS h_index,
        research_areas,
        NULL::JSONB                             AS therapeutic_areas,
        -- External identifiers from ORCID profile
        external_ids,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.orcid
    WHERE
        processed_to_silver = FALSE
        AND orcid_id IS NOT NULL
),

-- NIH Reporter grant counts per researcher, matched by PI name
-- pi_names is a JSONB array of {first_name, last_name, profile_id, ...}
nih_grant_counts AS (
    SELECT
        -- Normalize to LOWER for case-insensitive join
        LOWER(pi->>'first_name')    AS first_name_norm,
        LOWER(pi->>'last_name')     AS last_name_norm,
        COUNT(DISTINCT project_num) AS grant_count
    FROM mol_bronze.nih_reporter,
         -- COALESCE guards against JSON null literal (jsonb_typeof = 'null') which is stored
         -- as a non-SQL-NULL jsonb value; jsonb_array_elements fails on it with
         -- "cannot extract elements from a scalar".
         LATERAL jsonb_array_elements(
             CASE WHEN jsonb_typeof(pi_names) = 'array' THEN pi_names ELSE '[]'::jsonb END
         ) AS pi
    WHERE
        pi->>'last_name' IS NOT NULL
    GROUP BY
        LOWER(pi->>'first_name'),
        LOWER(pi->>'last_name')
)

SELECT
    id,
    orcid_id,
    given_name,
    family_name,
    credit_name,
    biography,
    affiliation,
    affiliations,
    country,
    works_count,
    h_index,
    research_areas,
    therapeutic_areas,
    external_ids,
    -- Grant count from NIH Reporter via name match (NULL if no match found)
    ngc.grant_count,
    source,
    source_updated_at,
    orcid_base.created_at,
    NOW()                           AS updated_at
FROM orcid_base
LEFT JOIN nih_grant_counts ngc
    ON  LOWER(orcid_base.given_name)  = ngc.first_name_norm
    AND LOWER(orcid_base.family_name) = ngc.last_name_norm;

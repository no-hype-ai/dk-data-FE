-- SQLMesh Model: Silver Researchers
-- Normalized researcher profile data from ORCID
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcp_silver.researchers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key orcid_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (orcid_id)),
        unique_values(columns := (orcid_id))
    ),
    grain orcid_id
);

SELECT
    gen_random_uuid() AS id,
    b.orcid_id,
    b.given_name,
    b.family_name,
    -- Full affiliations array preserved from bronze
    b.affiliations,
    -- Derived: primary affiliation for convenience
    b.affiliations->0->>'organization-name' AS affiliation,
    b.affiliations->0->>'country' AS country,
    b.works_count,
    -- H-index approximation (will be enriched externally)
    NULL::INTEGER AS h_index,
    b.research_areas,
    NULL::JSONB AS therapeutic_areas,
    NULL::INTEGER AS grant_count,
    b.id AS bronze_id,
    b.source,
    b.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM mol_bronze.orcid b
WHERE processed_to_silver = FALSE
  AND orcid_id IS NOT NULL;

-- SQLMesh Model: Bronze ORCID Researchers
-- Transforms raw.orcid structured rows into Bronze typed columns.
--
-- raw.orcid is populated by ORCIDFetcher + load_orcid_data() with explicit columns:
--   orcid_id VARCHAR(30) NOT NULL UNIQUE
--   given_names VARCHAR(255)
--   family_name VARCHAR(255)
--   credit_name VARCHAR(500)
--   biography TEXT
--   keywords JSONB            -- array of keyword strings
--   current_affiliations JSONB -- array of {organization, role, department}
--   works_count INTEGER        -- pre-computed count of works groups
--   external_ids JSONB         -- dict of {type: value} external identifiers
--   raw_response JSONB         -- full ORCID /record API response
--   fetched_at TIMESTAMPTZ
--   ingested_at TIMESTAMPTZ
--
-- Fixed (019-cms-puf-platform-reconciliation):
--   - Replaced all response_body JSONB extraction with direct structured columns
--   - Changed time_column from request_timestamp to fetched_at (actual column name)
--   - Removed non-existent WHERE predicates (response_status, processed_to_bronze)
--   - Fixed affiliations path: current_affiliations column (not response_body extraction)
--   - Fixed works_count: integer column (not JSON path)
--   - Fixed research_areas: keywords column (not research-resources JSON path)

MODEL (
    name bronze.orcid,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column fetched_at,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (orcid_id)),
        unique_values(columns := (orcid_id))
    ),
    grain orcid_id
);

SELECT
    gen_random_uuid()               AS id,

    -- Researcher identifiers (structured columns from raw.orcid)
    orcid_id,
    given_names                     AS given_name,
    family_name,
    credit_name,

    -- Affiliations: JSONB array of {organization, role, department}
    -- populated by ORCIDFetcher._parse_employments()
    current_affiliations            AS affiliations,

    -- Works count: integer column pre-computed by loader
    works_count,

    -- Research keywords: JSONB array of keyword strings
    -- (ORCID person.keywords; used as research_areas proxy)
    keywords                        AS research_areas,

    -- Source tracking
    id::TEXT                        AS raw_source_id,
    'orcid'                         AS source,
    fetched_at,
    fetched_at                      AS source_updated_at,
    FALSE                           AS processed_to_silver,
    NOW()                           AS created_at

FROM raw.orcid
WHERE
    orcid_id IS NOT NULL
    AND fetched_at BETWEEN @start_dt AND @end_dt;

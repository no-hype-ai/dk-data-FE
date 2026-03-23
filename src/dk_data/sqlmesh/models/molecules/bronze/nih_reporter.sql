-- SQLMesh Model: Bronze NIH Reporter
-- Extracts NIH Reporter grant records from mol_raw.nih_reporter JSON responses
-- into mol_bronze.nih_reporter with typed columns.
-- NIH Reporter API response structure:
--   response_body: { results: [{ projectNum, projectTitle, piProfiles, orgName, orgState,
--                               agencyCode, awardNoticeDate, projectStartDate, projectEndDate,
--                               abstractText, terms, phrText, totalCostAmount }] }
-- Part of: Tier 4 gap fix — nih_reporter cron was enabled but had no bronze transform

MODEL (
    name mol_bronze.nih_reporter,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    audits (
        not_null(columns := (project_number))
    ),
    grain (project_number)
);

WITH raw_grants AS (
    -- Unnest the results array from each raw API response
    SELECT
        r.id                                                        AS raw_source_id,
        r.request_timestamp,
        r.ingested_at,
        jsonb_array_elements(
            CASE
                WHEN jsonb_typeof(r.response_body->'results') = 'array'
                THEN r.response_body->'results'
                WHEN jsonb_typeof(r.response_body) = 'array'
                THEN r.response_body
                ELSE '[]'::jsonb
            END
        )                                                           AS grant_json
    FROM mol_raw.nih_reporter r
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body IS NOT NULL
      AND request_timestamp BETWEEN @start_dt AND @end_dt
)

SELECT
    gen_random_uuid()                                               AS id,
    raw_source_id,

    -- Project identifiers
    COALESCE(
        grant_json->>'projectNum',
        grant_json->>'project_num',
        grant_json->>'core_project_num'
    )                                                               AS project_number,
    COALESCE(
        grant_json->>'projectTitle',
        grant_json->>'project_title'
    )                                                               AS project_title,

    -- Principal Investigator — take first PI from piProfiles array
    COALESCE(
        (grant_json->'piProfiles'->0->>'firstName') || ' ' ||
        (grant_json->'piProfiles'->0->>'lastName'),
        grant_json->>'contact_pi_name'
    )                                                               AS pi_name,
    (grant_json->'piProfiles'->0->>'profileId')::BIGINT             AS pi_profile_id,

    -- Institution
    COALESCE(grant_json->>'orgName', grant_json->>'org_name')       AS pi_institution,
    COALESCE(grant_json->>'orgState', grant_json->>'org_state')     AS pi_institution_state,

    -- Funding
    COALESCE(grant_json->>'agencyCode', grant_json->>'agency_code') AS funding_ic,
    COALESCE(grant_json->>'agencyCode', 'NIH')                      AS funding_agency,
    COALESCE(
        (grant_json->>'totalCostAmount')::NUMERIC,
        (grant_json->>'award_amount')::NUMERIC
    )                                                               AS award_amount,
    COALESCE(
        (grant_json->>'fiscalYear')::INTEGER,
        (grant_json->>'fiscal_year')::INTEGER
    )                                                               AS fiscal_year,

    -- Dates
    COALESCE(
        (grant_json->>'projectStartDate')::DATE,
        (grant_json->>'project_start_date')::DATE
    )                                                               AS project_start,
    COALESCE(
        (grant_json->>'projectEndDate')::DATE,
        (grant_json->>'project_end_date')::DATE
    )                                                               AS project_end,

    -- Text fields
    COALESCE(grant_json->>'abstractText', grant_json->>'abstract_text') AS abstract_text,
    grant_json->>'terms'                                            AS terms,
    grant_json->>'phrText'                                          AS phr_text,

    -- Raw passthrough: individual grant record for column autodiscovery
    grant_json                                                      AS raw_json,

    -- Tracking
    'nih_reporter'                                                  AS source,
    request_timestamp,
    ingested_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM raw_grants
WHERE COALESCE(
    grant_json->>'projectNum',
    grant_json->>'project_num',
    grant_json->>'core_project_num'
) IS NOT NULL;

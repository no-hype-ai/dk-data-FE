-- SQLMesh Model: Bronze NIH Reporter Grants
-- Extracts typed fields from mol_raw.nih_reporter_raw JSONB responses.
-- Feature: 019-cms-puf-platform-reconciliation (T023)
--
-- Grain: project_num
-- Source: mol_raw.nih_reporter_raw (populated by NIHReporterFetcher via run_ingestion)
--
-- NIH Reporter API v2 POST /projects/search response fields (used here):
--   appl_id              INTEGER    — application ID (primary key in NIH system)
--   project_num          TEXT       — full project number (e.g. "R01CA123456")
--   project_title        TEXT
--   abstract_text        TEXT
--   full_study_section   TEXT       — study section name (may be absent; NULL if missing)
--   fiscal_year          INTEGER
--   activity_code        TEXT       — grant activity code (R01, R21, U01 …)
--   mechanism_code_dc    TEXT       — mechanism code
--   principal_investigators JSONB  — array of {profile_id, first_name, last_name, email, …}
--   program_officials    JSONB      — array of program officials
--   organization         JSONB      — object: {org_name, org_city, org_state, org_country}
--   award_amount         NUMERIC    — direct award amount
--   total_cost           NUMERIC    — total project cost (award_amount + indirect)
--   funding_mechanism    TEXT
--   terms                TEXT       — semicolon-delimited keyword terms
--   project_start_date   DATE       — ISO datetime string, cast to DATE
--   project_end_date     DATE       — ISO datetime string, cast to DATE

MODEL (
    name mol_bronze.nih_reporter,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key project_num
    ),
    cron '@weekly',
    audits (
        not_null(columns := (project_num, project_title))
    ),
    grain project_num
);

SELECT
    gen_random_uuid()                                               AS id,

    -- Core identifiers
    (response_body->>'appl_id')::INTEGER                           AS appl_id,
    response_body->>'project_num'                                   AS project_num,
    response_body->>'full_study_section'                            AS study_section,

    -- Project metadata
    response_body->>'project_title'                                 AS project_title,
    (response_body->>'fiscal_year')::INTEGER                        AS fiscal_year,
    response_body->>'activity_code'                                 AS activity_code,
    response_body->>'mechanism_code_dc'                             AS mechanism_code,

    -- Investigators (JSONB array: [{profile_id, first_name, last_name, email, …}])
    response_body->'principal_investigators'                        AS pi_names,
    response_body->'program_officials'                              AS program_officials,

    -- Organization (JSONB object: {org_name, org_city, org_state, org_country})
    response_body->'organization'->>'org_name'                      AS organization_name,
    response_body->'organization'->>'org_city'                      AS organization_city,
    response_body->'organization'->>'org_state'                     AS organization_state,
    response_body->'organization'->>'org_country'                   AS organization_country,

    -- Funding
    (response_body->>'award_amount')::NUMERIC                       AS award_amount,
    (response_body->>'total_cost')::NUMERIC                         AS total_cost,
    response_body->>'funding_mechanism'                             AS funding_mechanism,

    -- Abstract and keyword terms
    response_body->>'abstract_text'                                 AS abstract_text,
    response_body->>'terms'                                         AS terms,

    -- Dates (NIH API returns ISO datetime strings; ::DATE strips time component)
    (response_body->>'project_start_date')::DATE                    AS project_start_date,
    (response_body->>'project_end_date')::DATE                      AS project_end_date,

    -- Source tracking
    'nih_reporter'                                                  AS source,
    request_timestamp                                               AS source_updated_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM mol_raw.nih_reporter_raw
WHERE
    response_status = 200
    AND response_body->>'project_num' IS NOT NULL
    AND response_body->>'project_title' IS NOT NULL
    AND processed_to_bronze = FALSE;

-- SQLMesh Model: Bronze NIH Reporter Grants
-- Extracts typed fields from mol_raw.nih_reporter_raw JSONB responses.
-- Feature: 019-cms-puf-platform-reconciliation (T023)
--
-- Grain: project_number
-- Source: mol_raw.nih_reporter_raw (populated by NIHReporterFetcher via run_ingestion)

MODEL (
    name mol_bronze.nih_reporter,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key project_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (project_number, project_title))
    ),
    grain project_number
);

SELECT
    gen_random_uuid()                                               AS id,

    -- Core identifiers
    response_body->>'project_num'                                   AS project_number,
    response_body->>'full_study_section'                            AS study_section,

    -- Project metadata
    response_body->>'project_title'                                 AS project_title,
    (response_body->>'fiscal_year')::INTEGER                        AS fiscal_year,
    response_body->>'activity_code'                                 AS activity_code,
    response_body->>'mechanism_code_dc'                             AS mechanism_code,

    -- Investigators
    response_body->'principal_investigators'                        AS pi_names,
    response_body->'program_officials'                              AS program_officials,

    -- Organization
    response_body->'organization'->>'org_name'                      AS organization_name,
    response_body->'organization'->>'org_city'                      AS organization_city,
    response_body->'organization'->>'org_state'                     AS organization_state,
    response_body->'organization'->>'org_country'                   AS organization_country,

    -- Funding
    (response_body->>'award_amount')::NUMERIC                       AS award_amount,
    response_body->>'funding_mechanism'                             AS funding_mechanism,

    -- Abstract and terms
    response_body->>'abstract_text'                                 AS abstract_text,
    response_body->>'terms'                                         AS terms,

    -- Dates
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

-- SQLMesh Model: Bronze FDA REMS
-- Extracts REMS program records from mol_raw.fda_rems.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Source: OpenFDA drug/drugsfda endpoint, REMS submissions filter.
-- Each mol_raw.fda_rems row is one NDA/ANDA/BLA application that has
-- at least one submission with submission_type == "REMS".
--
-- OpenFDA drugsfda application fields:
--   application_number, sponsor_name, openfda.brand_name, openfda.generic_name,
--   submissions[].submission_type, submissions[].submission_number,
--   submissions[].submission_status, submissions[].submission_status_date,
--   submissions[].submission_class_code, submissions[].rems_required_files

MODEL (
    name mol_bronze.fda_rems,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key application_number
    ),
    cron '@monthly',
    audits (
        not_null(columns := (application_number))
    ),
    grain application_number,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH rems_apps AS (
    SELECT
        raw.id          AS raw_source_id,
        raw.ingested_at,
        raw.response_body AS app
    FROM mol_raw.fda_rems AS raw
    WHERE raw.response_status = 200
      AND raw.ingested_at BETWEEN @start_dt AND @end_dt
),

-- Extract the first REMS submission per application for key REMS fields
rems_submissions AS (
    SELECT
        raw_source_id,
        ingested_at,
        app,
        -- Find the most recent REMS submission (submission_class_code = 'REMS')
        (
            SELECT sub
            FROM jsonb_array_elements(COALESCE(app->'submissions', '[]'::JSONB)) AS sub
            WHERE sub->>'submission_class_code' = 'REMS'
            ORDER BY sub->>'submission_status_date' DESC
            LIMIT 1
        ) AS rems_sub,
        -- Initial REMS submission (earliest)
        (
            SELECT sub
            FROM jsonb_array_elements(COALESCE(app->'submissions', '[]'::JSONB)) AS sub
            WHERE sub->>'submission_class_code' = 'REMS'
            ORDER BY sub->>'submission_status_date' ASC
            LIMIT 1
        ) AS first_rems_sub
    FROM rems_apps
    WHERE EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(app->'submissions', '[]'::JSONB)) AS sub
        WHERE sub->>'submission_class_code' = 'REMS'
    )
),

deduped AS (
    SELECT DISTINCT ON (app->>'application_number')
        raw_source_id,
        ingested_at,
        app,
        rems_sub,
        first_rems_sub
    FROM rems_submissions
    ORDER BY app->>'application_number', ingested_at DESC
)

SELECT
    gen_random_uuid()                                                   AS id,

    app->>'application_number'                                          AS application_number,
    app->>'sponsor_name'                                                AS sponsor_name,

    -- Brand and generic name from openfda nested object (array → first element)
    (app->'openfda'->'brand_name'->>0)                                  AS brand_name,
    (app->'openfda'->'generic_name'->>0)                                AS generic_name,

    -- Application type from number prefix (NDA/ANDA/BLA)
    CASE
        WHEN app->>'application_number' LIKE 'NDA%'  THEN 'NDA'
        WHEN app->>'application_number' LIKE 'ANDA%' THEN 'ANDA'
        WHEN app->>'application_number' LIKE 'BLA%'  THEN 'BLA'
        ELSE NULL
    END                                                                 AS application_type,

    -- REMS status from the most recent REMS submission
    rems_sub->>'submission_status'                                      AS rems_status,

    -- Submission class code maps to REMS type (e.g. REMS, REMS-ETASU)
    rems_sub->>'submission_class_code'                                  AS rems_type,

    -- Dates
    (first_rems_sub->>'submission_status_date')::DATE                   AS initial_approval_date,
    (rems_sub->>'submission_status_date')::DATE                         AS most_recent_modification,

    -- Required REMS elements (file list from rems_required_files)
    ARRAY(
        SELECT elem->>'file_name'
        FROM jsonb_array_elements(COALESCE(rems_sub->'rems_required_files', '[]'::JSONB)) AS elem
        WHERE elem->>'file_name' IS NOT NULL
    )                                                                   AS elements,

    -- Source URL (FDA product page)
    'https://www.accessdata.fda.gov/scripts/cder/rems/index.cfm?event=IndvREMS.page&REMS='
        || (app->>'application_number')                                 AS url,

    -- Source tracking
    app                                                                 AS raw_json,
    raw_source_id,
    'fda_rems'                                                          AS source,
    ingested_at,
    ingested_at                                                         AS source_updated_at,
    FALSE                                                               AS processed_to_silver,
    NOW()                                                               AS created_at

FROM deduped
WHERE app->>'application_number' IS NOT NULL;

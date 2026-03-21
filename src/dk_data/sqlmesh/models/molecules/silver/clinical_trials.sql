-- SQLMesh Model: Silver Clinical Trials
-- Transforms Bronze ClinicalTrials.gov data to normalized Silver layer
-- Part of: 012-dk-data-platform

MODEL (
    name silver.clinical_trials,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key nct_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (nct_id, title)),
        unique_values(columns := (nct_id))
    ),
    grain nct_id
);

SELECT
    gen_random_uuid() AS trial_id,

    -- External Identifiers
    raw_data->>'nctId' AS nct_id,
    raw_data->'protocolSection'->'identificationModule'->>'orgStudyIdInfo' AS org_study_id,

    -- Title
    raw_data->'protocolSection'->'identificationModule'->>'briefTitle' AS title,
    raw_data->'protocolSection'->'identificationModule'->>'officialTitle' AS official_title,

    -- Summary
    raw_data->'protocolSection'->'descriptionModule'->>'briefSummary' AS brief_summary,
    raw_data->'protocolSection'->'descriptionModule'->>'detailedDescription' AS detailed_description,

    -- Phase & Status
    CASE
        WHEN raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 1%' AND
             raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 2%'
        THEN 'Phase 1/2'
        WHEN raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 2%' AND
             raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 3%'
        THEN 'Phase 2/3'
        WHEN raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 1%' THEN 'Phase 1'
        WHEN raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 2%' THEN 'Phase 2'
        WHEN raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 3%' THEN 'Phase 3'
        WHEN raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Phase 4%' THEN 'Phase 4'
        WHEN raw_data->'protocolSection'->'designModule'->>'phases' LIKE '%Early%' THEN 'Early Phase 1'
        ELSE 'Not Applicable'
    END AS phase,

    raw_data->'protocolSection'->'statusModule'->>'overallStatus' AS overall_status,

    -- Dates
    (raw_data->'protocolSection'->'statusModule'->'startDateStruct'->>'date')::DATE AS start_date,
    (raw_data->'protocolSection'->'statusModule'->'completionDateStruct'->>'date')::DATE AS completion_date,
    (raw_data->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date')::DATE AS primary_completion_date,
    (raw_data->'protocolSection'->'statusModule'->'completionDateStruct'->>'date')::DATE AS end_date,

    -- Conditions (as JSONB array)
    raw_data->'protocolSection'->'conditionsModule'->'conditions' AS conditions,

    -- Interventions
    raw_data->'protocolSection'->'armsInterventionsModule'->'interventions' AS interventions,

    -- Study Design
    raw_data->'protocolSection'->'designModule'->>'studyType' AS study_type,
    raw_data->'protocolSection'->'designModule'->'designInfo'->>'allocation' AS allocation,
    raw_data->'protocolSection'->'designModule'->'designInfo'->>'interventionModel' AS intervention_model,
    raw_data->'protocolSection'->'designModule'->'designInfo'->'maskingInfo'->>'masking' AS masking,
    (raw_data->'protocolSection'->'designModule'->'enrollmentInfo'->>'count')::INTEGER AS enrollment,

    -- Sponsors
    raw_data->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'name' AS lead_sponsor,
    raw_data->'protocolSection'->'sponsorCollaboratorsModule'->'collaborators' AS collaborators,

    -- Outcomes
    raw_data->'protocolSection'->'outcomesModule'->'primaryOutcomes' AS primary_outcomes,
    raw_data->'protocolSection'->'outcomesModule'->'secondaryOutcomes' AS secondary_outcomes,

    -- Results
    (raw_data->'hasResults')::BOOLEAN AS has_results,

    -- Source Tracking
    id AS bronze_id,
    'clinicaltrials_gov' AS source,
    ingested_at,
    ingested_at AS source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM bronze_clinicaltrials
WHERE
    processed_to_silver = FALSE
    AND raw_data->>'nctId' IS NOT NULL
    AND ingested_at BETWEEN @start_dt AND @end_dt;

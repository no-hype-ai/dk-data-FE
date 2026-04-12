-- SQLMesh Model: Bronze ClinicalTrials
-- Transforms Raw ClinicalTrials.gov batch responses (response_body->studies[])
-- to Bronze typed columns with one row per study.
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.clinicaltrials,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key nct_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (nct_id)),
        unique_values(columns := (nct_id))
    ),
    grain nct_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Unnest the studies array from batch API responses.
-- Each raw row may contain up to 1000 studies under response_body->'studies'.
-- Also handles legacy single-study rows (response_body->'protocolSection' directly).
WITH studies AS (
    SELECT
        r.id           AS raw_source_id,
        r.request_timestamp,
        study.value    AS study
    FROM mol_raw.clinicaltrials r
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN r.response_body ? 'studies'
            THEN r.response_body->'studies'
            ELSE jsonb_build_array(r.response_body)
        END
    ) AS study(value)
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
)

SELECT
    gen_random_uuid() AS id,

    -- NCT Identifier
    study->'protocolSection'->'identificationModule'->>'nctId' AS nct_id,
    study->'protocolSection'->'identificationModule'->'orgStudyIdInfo'->>'textId' AS org_study_id,

    -- Titles
    study->'protocolSection'->'identificationModule'->>'briefTitle' AS brief_title,
    study->'protocolSection'->'identificationModule'->>'officialTitle' AS official_title,
    study->'protocolSection'->'identificationModule'->>'acronym' AS acronym,

    -- Summary
    study->'protocolSection'->'descriptionModule'->>'briefSummary' AS brief_summary,
    study->'protocolSection'->'descriptionModule'->>'detailedDescription' AS detailed_description,

    -- Status
    study->'protocolSection'->'statusModule'->>'overallStatus' AS overall_status,
    study->'protocolSection'->'statusModule'->>'lastKnownStatus' AS last_known_status,
    study->'protocolSection'->'statusModule'->>'whyStopped' AS why_stopped,

    -- Dates (guard against partial dates like "2009-03" which cannot cast to DATE)
    CASE WHEN (study->'protocolSection'->'statusModule'->'startDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (study->'protocolSection'->'statusModule'->'startDateStruct'->>'date')::DATE END AS start_date,
    CASE WHEN (study->'protocolSection'->'statusModule'->'completionDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (study->'protocolSection'->'statusModule'->'completionDateStruct'->>'date')::DATE END AS completion_date,
    CASE WHEN (study->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (study->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date')::DATE END AS primary_completion_date,
    CASE WHEN (study->'protocolSection'->'statusModule'->>'studyFirstSubmitDate') ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (study->'protocolSection'->'statusModule'->>'studyFirstSubmitDate')::DATE END AS first_submit_date,
    CASE WHEN (study->'protocolSection'->'statusModule'->'studyFirstPostDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (study->'protocolSection'->'statusModule'->'studyFirstPostDateStruct'->>'date')::DATE END AS first_post_date,
    CASE WHEN (study->'protocolSection'->'statusModule'->'lastUpdatePostDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (study->'protocolSection'->'statusModule'->'lastUpdatePostDateStruct'->>'date')::DATE END AS last_update_date,

    -- Design
    study->'protocolSection'->'designModule'->>'studyType' AS study_type,
    study->'protocolSection'->'designModule'->'phases'::JSONB AS phases,
    study->'protocolSection'->'designModule'->'designInfo'->>'allocation' AS allocation,
    study->'protocolSection'->'designModule'->'designInfo'->>'interventionModel' AS intervention_model,
    study->'protocolSection'->'designModule'->'designInfo'->'maskingInfo'->>'masking' AS masking,
    (study->'protocolSection'->'designModule'->'enrollmentInfo'->>'count')::INTEGER AS enrollment_count,
    study->'protocolSection'->'designModule'->'enrollmentInfo'->>'type' AS enrollment_type,

    -- Conditions
    study->'protocolSection'->'conditionsModule'->'conditions'::JSONB AS conditions,
    study->'protocolSection'->'conditionsModule'->'keywords'::JSONB AS keywords,

    -- Interventions
    study->'protocolSection'->'armsInterventionsModule'->'interventions'::JSONB AS interventions,
    study->'protocolSection'->'armsInterventionsModule'->'armGroups'::JSONB AS arm_groups,

    -- Eligibility
    study->'protocolSection'->'eligibilityModule'->>'sex' AS eligibility_sex,
    study->'protocolSection'->'eligibilityModule'->>'minimumAge' AS minimum_age,
    study->'protocolSection'->'eligibilityModule'->>'maximumAge' AS maximum_age,
    study->'protocolSection'->'eligibilityModule'->>'healthyVolunteers' AS healthy_volunteers,
    study->'protocolSection'->'eligibilityModule'->>'eligibilityCriteria' AS eligibility_criteria,

    -- Sponsors
    study->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'name' AS lead_sponsor_name,
    study->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'class' AS lead_sponsor_class,
    study->'protocolSection'->'sponsorCollaboratorsModule'->'collaborators'::JSONB AS collaborators,
    study->'protocolSection'->'sponsorCollaboratorsModule'->'responsibleParty'::JSONB AS responsible_party,

    -- Contacts
    study->'protocolSection'->'contactsLocationsModule'->'centralContacts'::JSONB AS central_contacts,
    study->'protocolSection'->'contactsLocationsModule'->'locations'::JSONB AS locations,

    -- Outcomes
    study->'protocolSection'->'outcomesModule'->'primaryOutcomes'::JSONB AS primary_outcomes,
    study->'protocolSection'->'outcomesModule'->'secondaryOutcomes'::JSONB AS secondary_outcomes,

    -- Results
    (study->>'hasResults')::BOOLEAN AS has_results,
    study->'resultsSection'::JSONB AS results_section,

    -- Raw source tracking
    study AS raw_json,
    raw_source_id,
    'clinicaltrials_gov' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM (
    SELECT DISTINCT ON (study->'protocolSection'->'identificationModule'->>'nctId')
        *
    FROM studies
    WHERE study->'protocolSection'->'identificationModule'->>'nctId' IS NOT NULL
    ORDER BY study->'protocolSection'->'identificationModule'->>'nctId',
             request_timestamp DESC
) deduped;

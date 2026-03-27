-- SQLMesh Model: Bronze ClinicalTrials
-- Transforms Raw ClinicalTrials.gov responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name bronze.clinicaltrials,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (nct_id)),
        unique_values(columns := (nct_id))
    ),
    grain nct_id
);

SELECT
    gen_random_uuid() AS id,

    -- NCT Identifier
    response_body->'protocolSection'->'identificationModule'->>'nctId' AS nct_id,
    -- orgStudyIdInfo is an object {textId, type}; extract the textId string
    response_body->'protocolSection'->'identificationModule'->'orgStudyIdInfo'->>'textId' AS org_study_id,

    -- Titles
    response_body->'protocolSection'->'identificationModule'->>'briefTitle' AS brief_title,
    response_body->'protocolSection'->'identificationModule'->>'officialTitle' AS official_title,
    response_body->'protocolSection'->'identificationModule'->>'acronym' AS acronym,

    -- Summary
    response_body->'protocolSection'->'descriptionModule'->>'briefSummary' AS brief_summary,
    response_body->'protocolSection'->'descriptionModule'->>'detailedDescription' AS detailed_description,

    -- Status
    response_body->'protocolSection'->'statusModule'->>'overallStatus' AS overall_status,
    response_body->'protocolSection'->'statusModule'->>'lastKnownStatus' AS last_known_status,
    response_body->'protocolSection'->'statusModule'->>'whyStopped' AS why_stopped,

    -- Dates (startDateStruct / completionDateStruct / primaryCompletionDateStruct are objects with {date, type})
    (response_body->'protocolSection'->'statusModule'->'startDateStruct'->>'date')::DATE AS start_date,
    (response_body->'protocolSection'->'statusModule'->'completionDateStruct'->>'date')::DATE AS completion_date,
    (response_body->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date')::DATE AS primary_completion_date,
    (response_body->'protocolSection'->'statusModule'->>'studyFirstSubmitDate')::DATE AS first_submit_date,
    -- studyFirstPostDateStruct and lastUpdatePostDateStruct are objects with {date, type}
    (response_body->'protocolSection'->'statusModule'->'studyFirstPostDateStruct'->>'date')::DATE AS first_post_date,
    (response_body->'protocolSection'->'statusModule'->'lastUpdatePostDateStruct'->>'date')::DATE AS last_update_date,

    -- Design
    response_body->'protocolSection'->'designModule'->>'studyType' AS study_type,
    -- phases is a JSON array (e.g. ["PHASE1", "PHASE2"])
    response_body->'protocolSection'->'designModule'->'phases'::JSONB AS phases,
    response_body->'protocolSection'->'designModule'->'designInfo'->>'allocation' AS allocation,
    response_body->'protocolSection'->'designModule'->'designInfo'->>'interventionModel' AS intervention_model,
    response_body->'protocolSection'->'designModule'->'designInfo'->'maskingInfo'->>'masking' AS masking,
    (response_body->'protocolSection'->'designModule'->'enrollmentInfo'->>'count')::INTEGER AS enrollment_count,
    response_body->'protocolSection'->'designModule'->'enrollmentInfo'->>'type' AS enrollment_type,

    -- Conditions (JSON arrays)
    response_body->'protocolSection'->'conditionsModule'->'conditions'::JSONB AS conditions,
    response_body->'protocolSection'->'conditionsModule'->'keywords'::JSONB AS keywords,

    -- Interventions (JSON arrays)
    response_body->'protocolSection'->'armsInterventionsModule'->'interventions'::JSONB AS interventions,
    response_body->'protocolSection'->'armsInterventionsModule'->'armGroups'::JSONB AS arm_groups,

    -- Eligibility
    response_body->'protocolSection'->'eligibilityModule'->>'sex' AS eligibility_sex,
    response_body->'protocolSection'->'eligibilityModule'->>'minimumAge' AS minimum_age,
    response_body->'protocolSection'->'eligibilityModule'->>'maximumAge' AS maximum_age,
    response_body->'protocolSection'->'eligibilityModule'->>'healthyVolunteers' AS healthy_volunteers,
    response_body->'protocolSection'->'eligibilityModule'->>'eligibilityCriteria' AS eligibility_criteria,

    -- Sponsors
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'name' AS lead_sponsor_name,
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'class' AS lead_sponsor_class,
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'collaborators'::JSONB AS collaborators,
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'responsibleParty'::JSONB AS responsible_party,

    -- Contacts
    response_body->'protocolSection'->'contactsLocationsModule'->'centralContacts'::JSONB AS central_contacts,
    response_body->'protocolSection'->'contactsLocationsModule'->'locations'::JSONB AS locations,

    -- Outcomes
    response_body->'protocolSection'->'outcomesModule'->'primaryOutcomes'::JSONB AS primary_outcomes,
    response_body->'protocolSection'->'outcomesModule'->'secondaryOutcomes'::JSONB AS secondary_outcomes,

    -- Results (hasResults is a top-level field in the v2 API response)
    (response_body->>'hasResults')::BOOLEAN AS has_results,
    response_body->'resultsSection'::JSONB AS results_section,

    -- Raw source tracking
    response_body AS raw_json,
    -- raw_source_id references the raw table PK, not the generated bronze id
    raw.clinicaltrials.id AS raw_source_id,
    'clinicaltrials_gov' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.clinicaltrials
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->'protocolSection'->'identificationModule'->>'nctId' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;

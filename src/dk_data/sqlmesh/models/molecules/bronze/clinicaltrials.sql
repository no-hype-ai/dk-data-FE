-- SQLMesh Model: Bronze ClinicalTrials
-- Transforms Raw ClinicalTrials.gov responses to Bronze typed columns
-- Handles both bulk search responses ({studies: [...]}) and individual study responses ({protocolSection: ...})
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.clinicaltrials,
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

-- Expand bulk search responses (response_body->'studies'[]) and individual study responses
-- DISTINCT ON nct_id deduplicates trials that appear in multiple search result pages
WITH expanded AS (
    SELECT
        raw.id              AS raw_source_id,
        raw.request_timestamp,
        raw.request_params->>'query.intr' AS queried_drug_name,
        study.value         AS s
    FROM mol_raw.clinicaltrials AS raw,
    LATERAL jsonb_array_elements(
        CASE
            WHEN raw.response_body ? 'studies'         THEN raw.response_body->'studies'
            WHEN raw.response_body ? 'protocolSection' THEN jsonb_build_array(raw.response_body)
            ELSE '[]'::jsonb
        END
    ) AS study(value)
    WHERE raw.response_status = 200
      AND raw.processed_to_bronze = FALSE
      AND raw.request_timestamp BETWEEN @start_dt AND @end_dt
),
deduped AS (
    -- Keep one row per nct_id; prefer rows from a named drug query over generic searches
    SELECT DISTINCT ON (s->'protocolSection'->'identificationModule'->>'nctId')
        raw_source_id, request_timestamp, queried_drug_name, s
    FROM expanded
    WHERE s->'protocolSection'->'identificationModule'->>'nctId' IS NOT NULL
    ORDER BY s->'protocolSection'->'identificationModule'->>'nctId',
             (queried_drug_name IS NOT NULL) DESC,
             request_timestamp DESC
)

SELECT
    gen_random_uuid() AS id,

    -- NCT Identifier
    s->'protocolSection'->'identificationModule'->>'nctId' AS nct_id,
    s->'protocolSection'->'identificationModule'->>'orgStudyIdInfo' AS org_study_id,

    -- Titles
    s->'protocolSection'->'identificationModule'->>'briefTitle' AS brief_title,
    s->'protocolSection'->'identificationModule'->>'officialTitle' AS official_title,
    s->'protocolSection'->'identificationModule'->>'acronym' AS acronym,

    -- Summary
    s->'protocolSection'->'descriptionModule'->>'briefSummary' AS brief_summary,
    s->'protocolSection'->'descriptionModule'->>'detailedDescription' AS detailed_description,

    -- Status
    s->'protocolSection'->'statusModule'->>'overallStatus' AS overall_status,
    s->'protocolSection'->'statusModule'->>'lastKnownStatus' AS last_known_status,
    s->'protocolSection'->'statusModule'->>'whyStopped' AS why_stopped,

    -- Dates
    s->'protocolSection'->'statusModule'->'startDateStruct'->>'date' AS start_date,
    s->'protocolSection'->'statusModule'->'completionDateStruct'->>'date' AS completion_date,
    s->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date' AS primary_completion_date,
    s->'protocolSection'->'statusModule'->>'studyFirstSubmitDate' AS first_submit_date,
    s->'protocolSection'->'statusModule'->>'studyFirstPostDateStruct' AS first_post_date,
    s->'protocolSection'->'statusModule'->>'lastUpdatePostDateStruct' AS last_update_date,

    -- Design
    s->'protocolSection'->'designModule'->>'studyType' AS study_type,
    s->'protocolSection'->'designModule'->'phases' AS phases,
    s->'protocolSection'->'designModule'->'designInfo'->>'allocation' AS allocation,
    s->'protocolSection'->'designModule'->'designInfo'->>'interventionModel' AS intervention_model,
    s->'protocolSection'->'designModule'->'designInfo'->'maskingInfo'->>'masking' AS masking,
    (s->'protocolSection'->'designModule'->'enrollmentInfo'->>'count')::INTEGER AS enrollment_count,
    s->'protocolSection'->'designModule'->'enrollmentInfo'->>'type' AS enrollment_type,

    -- Conditions
    s->'protocolSection'->'conditionsModule'->'conditions' AS conditions,
    s->'protocolSection'->'conditionsModule'->'keywords' AS keywords,

    -- Interventions
    s->'protocolSection'->'armsInterventionsModule'->'interventions' AS interventions,
    s->'protocolSection'->'armsInterventionsModule'->'armGroups' AS arm_groups,

    -- Eligibility
    s->'protocolSection'->'eligibilityModule'->>'sex' AS eligibility_sex,
    s->'protocolSection'->'eligibilityModule'->>'minimumAge' AS minimum_age,
    s->'protocolSection'->'eligibilityModule'->>'maximumAge' AS maximum_age,
    s->'protocolSection'->'eligibilityModule'->>'healthyVolunteers' AS healthy_volunteers,
    s->'protocolSection'->'eligibilityModule'->>'eligibilityCriteria' AS eligibility_criteria,

    -- Sponsors
    s->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'name' AS lead_sponsor_name,
    s->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'class' AS lead_sponsor_class,
    s->'protocolSection'->'sponsorCollaboratorsModule'->'collaborators' AS collaborators,
    s->'protocolSection'->'sponsorCollaboratorsModule'->'responsibleParty' AS responsible_party,

    -- Contacts
    s->'protocolSection'->'contactsLocationsModule'->'centralContacts' AS central_contacts,
    s->'protocolSection'->'contactsLocationsModule'->'locations' AS locations,

    -- Outcomes
    s->'protocolSection'->'outcomesModule'->'primaryOutcomes' AS primary_outcomes,
    s->'protocolSection'->'outcomesModule'->'secondaryOutcomes' AS secondary_outcomes,

    -- Oversight (FDA regulatory status)
    (s->'protocolSection'->'oversightModule'->>'isFdaRegulatedDrug')::BOOLEAN AS fda_regulated_drug,
    (s->'protocolSection'->'oversightModule'->>'isFdaRegulatedDevice')::BOOLEAN AS fda_regulated_device,
    (s->'protocolSection'->'oversightModule'->>'isUnapprovedDevice')::BOOLEAN AS is_unapproved_device,
    s->'protocolSection'->'oversightModule'->'oversightHasDmc' AS has_dmc,

    -- References (PMIDs, citations)
    s->'protocolSection'->'referencesModule'->'references' AS references,
    s->'protocolSection'->'referencesModule'->'seeAlsoLinks' AS see_also_links,

    -- IPD Sharing
    s->'protocolSection'->'ipdSharingStatementModule'->>'ipdSharing' AS ipd_sharing,
    s->'protocolSection'->'ipdSharingStatementModule'->>'description' AS ipd_sharing_description,
    s->'protocolSection'->'ipdSharingStatementModule'->'infoTypes' AS ipd_sharing_info_types,
    s->'protocolSection'->'ipdSharingStatementModule'->>'timeFrame' AS ipd_sharing_time_frame,
    s->'protocolSection'->'ipdSharingStatementModule'->>'accessCriteria' AS ipd_sharing_access_criteria,

    -- Other Outcomes
    s->'protocolSection'->'outcomesModule'->'otherOutcomes' AS other_outcomes,

    -- Results
    (s->>'hasResults')::BOOLEAN AS has_results,
    s->'resultsSection' AS results_section,
    s->'resultsSection'->'participantFlowModule' AS results_participant_flow,
    s->'resultsSection'->'baselineCharacteristicsModule' AS results_baseline,
    s->'resultsSection'->'outcomeMeasuresModule'->'outcomeMeasures' AS results_outcome_measures,
    s->'resultsSection'->'adverseEventsModule' AS results_adverse_events,
    s->'resultsSection'->'moreInfoModule' AS results_more_info,

    -- Derived Section (MeSH browse hierarchies)
    s->'derivedSection'->'conditionBrowseModule' AS condition_browse,
    s->'derivedSection'->'interventionBrowseModule' AS intervention_browse,
    s->'derivedSection'->'miscInfoModule' AS misc_info,

    -- Raw source tracking
    s AS raw_json,
    raw_source_id,
    'clinicaltrials_gov' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at,

    -- Drug name from original API query — used for direct entity linking in silver
    -- (avoids unreliable fuzzy title matching)
    queried_drug_name

FROM deduped;

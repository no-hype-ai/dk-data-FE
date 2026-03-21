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
    response_body->'protocolSection'->'identificationModule'->>'orgStudyIdInfo' AS org_study_id,

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

    -- Dates
    response_body->'protocolSection'->'statusModule'->'startDateStruct'->>'date' AS start_date,
    response_body->'protocolSection'->'statusModule'->'completionDateStruct'->>'date' AS completion_date,
    response_body->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date' AS primary_completion_date,
    response_body->'protocolSection'->'statusModule'->>'studyFirstSubmitDate' AS first_submit_date,
    response_body->'protocolSection'->'statusModule'->>'studyFirstPostDateStruct' AS first_post_date,
    response_body->'protocolSection'->'statusModule'->>'lastUpdatePostDateStruct' AS last_update_date,

    -- Design
    response_body->'protocolSection'->'designModule'->>'studyType' AS study_type,
    response_body->'protocolSection'->'designModule'->'phases' AS phases,
    response_body->'protocolSection'->'designModule'->'designInfo'->>'allocation' AS allocation,
    response_body->'protocolSection'->'designModule'->'designInfo'->>'interventionModel' AS intervention_model,
    response_body->'protocolSection'->'designModule'->'designInfo'->'maskingInfo'->>'masking' AS masking,
    (response_body->'protocolSection'->'designModule'->'enrollmentInfo'->>'count')::INTEGER AS enrollment_count,
    response_body->'protocolSection'->'designModule'->'enrollmentInfo'->>'type' AS enrollment_type,

    -- Conditions
    response_body->'protocolSection'->'conditionsModule'->'conditions' AS conditions,
    response_body->'protocolSection'->'conditionsModule'->'keywords' AS keywords,

    -- Interventions
    response_body->'protocolSection'->'armsInterventionsModule'->'interventions' AS interventions,
    response_body->'protocolSection'->'armsInterventionsModule'->'armGroups' AS arm_groups,

    -- Eligibility
    response_body->'protocolSection'->'eligibilityModule'->>'sex' AS eligibility_sex,
    response_body->'protocolSection'->'eligibilityModule'->>'minimumAge' AS minimum_age,
    response_body->'protocolSection'->'eligibilityModule'->>'maximumAge' AS maximum_age,
    response_body->'protocolSection'->'eligibilityModule'->>'healthyVolunteers' AS healthy_volunteers,
    response_body->'protocolSection'->'eligibilityModule'->>'eligibilityCriteria' AS eligibility_criteria,

    -- Sponsors
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'name' AS lead_sponsor_name,
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'class' AS lead_sponsor_class,
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'collaborators' AS collaborators,
    response_body->'protocolSection'->'sponsorCollaboratorsModule'->'responsibleParty' AS responsible_party,

    -- Contacts
    response_body->'protocolSection'->'contactsLocationsModule'->'centralContacts' AS central_contacts,
    response_body->'protocolSection'->'contactsLocationsModule'->'locations' AS locations,

    -- Outcomes
    response_body->'protocolSection'->'outcomesModule'->'primaryOutcomes' AS primary_outcomes,
    response_body->'protocolSection'->'outcomesModule'->'secondaryOutcomes' AS secondary_outcomes,

    -- Oversight (FDA regulatory status)
    (response_body->'protocolSection'->'oversightModule'->>'isFdaRegulatedDrug')::BOOLEAN AS fda_regulated_drug,
    (response_body->'protocolSection'->'oversightModule'->>'isFdaRegulatedDevice')::BOOLEAN AS fda_regulated_device,
    (response_body->'protocolSection'->'oversightModule'->>'isUnapprovedDevice')::BOOLEAN AS is_unapproved_device,
    response_body->'protocolSection'->'oversightModule'->'oversightHasDmc' AS has_dmc,

    -- References (PMIDs, citations)
    response_body->'protocolSection'->'referencesModule'->'references' AS references,
    response_body->'protocolSection'->'referencesModule'->'seeAlsoLinks' AS see_also_links,

    -- IPD Sharing
    response_body->'protocolSection'->'ipdSharingStatementModule'->>'ipdSharing' AS ipd_sharing,
    response_body->'protocolSection'->'ipdSharingStatementModule'->>'description' AS ipd_sharing_description,
    response_body->'protocolSection'->'ipdSharingStatementModule'->'infoTypes' AS ipd_sharing_info_types,
    response_body->'protocolSection'->'ipdSharingStatementModule'->>'timeFrame' AS ipd_sharing_time_frame,
    response_body->'protocolSection'->'ipdSharingStatementModule'->>'accessCriteria' AS ipd_sharing_access_criteria,

    -- Other Outcomes
    response_body->'protocolSection'->'outcomesModule'->'otherOutcomes' AS other_outcomes,

    -- Results
    (response_body->>'hasResults')::BOOLEAN AS has_results,
    response_body->'resultsSection' AS results_section,
    response_body->'resultsSection'->'participantFlowModule' AS results_participant_flow,
    response_body->'resultsSection'->'baselineCharacteristicsModule' AS results_baseline,
    response_body->'resultsSection'->'outcomeMeasuresModule'->'outcomeMeasures' AS results_outcome_measures,
    response_body->'resultsSection'->'adverseEventsModule' AS results_adverse_events,
    response_body->'resultsSection'->'moreInfoModule' AS results_more_info,

    -- Derived Section (MeSH browse hierarchies)
    response_body->'derivedSection'->'conditionBrowseModule' AS condition_browse,
    response_body->'derivedSection'->'interventionBrowseModule' AS intervention_browse,
    response_body->'derivedSection'->'miscInfoModule' AS misc_info,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'clinicaltrials_gov' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.clinicaltrials
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->'protocolSection'->'identificationModule'->>'nctId' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;

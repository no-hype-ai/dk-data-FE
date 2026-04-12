-- Migration 031/032: Tray procedure for mol_bronze.clinicaltrials
-- Audit fix (2026-04-12): replaces the bronze→bronze stub with a real raw→bronze
-- rebuild that mirrors src/dk_data/sqlmesh/models/molecules/bronze/clinicaltrials.sql.

CREATE OR REPLACE PROCEDURE mol_bronze.refresh_clinicaltrials_via_tray()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size CONSTANT BIGINT := 1000;
    v_proc_name  CONSTANT TEXT := 'mol_bronze.refresh_clinicaltrials_via_tray';
    v_max_raw_id BIGINT;
    v_low_id     BIGINT := 0;
    v_high_id    BIGINT;
    v_chunk_pos  INT := 0;
    v_chunk_rows INT;
    v_total_rows BIGINT := 0;
    v_wal_start  pg_lsn;
    v_wal_end    pg_lsn;
    v_wal_bytes  BIGINT;
BEGIN
    CALL mol_bronze._tray_setup(v_proc_name, 'mol_bronze', 'clinicaltrials', 'clinicaltrials_tray');
    SET LOCAL work_mem = '128MB';

    SELECT COALESCE(MAX(id), 0) INTO v_max_raw_id FROM mol_raw.clinicaltrials;

    WHILE v_low_id < v_max_raw_id LOOP
        v_high_id := v_low_id + v_chunk_size;
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

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
            WHERE r.id > v_low_id AND r.id <= v_high_id
              AND r.response_status = 200
        ),
        deduped AS (
            SELECT DISTINCT ON (study->'protocolSection'->'identificationModule'->>'nctId') *
            FROM studies
            WHERE study->'protocolSection'->'identificationModule'->>'nctId' IS NOT NULL
            ORDER BY study->'protocolSection'->'identificationModule'->>'nctId', request_timestamp DESC
        )
        INSERT INTO mol_bronze.clinicaltrials_tray (
            id, nct_id, org_study_id, brief_title, official_title, acronym,
            brief_summary, detailed_description, overall_status, last_known_status, why_stopped,
            start_date, completion_date, primary_completion_date, first_submit_date,
            first_post_date, last_update_date,
            study_type, phases, allocation, intervention_model, masking,
            enrollment_count, enrollment_type, conditions, keywords, interventions, arm_groups,
            eligibility_sex, minimum_age, maximum_age, healthy_volunteers, eligibility_criteria,
            lead_sponsor_name, lead_sponsor_class, collaborators, responsible_party,
            central_contacts, locations, primary_outcomes, secondary_outcomes,
            has_results, results_section,
            raw_json, raw_source_id, source, request_timestamp, source_updated_at,
            processed_to_silver, created_at
        )
        SELECT
            gen_random_uuid(),
            study->'protocolSection'->'identificationModule'->>'nctId',
            study->'protocolSection'->'identificationModule'->'orgStudyIdInfo'->>'textId',
            study->'protocolSection'->'identificationModule'->>'briefTitle',
            study->'protocolSection'->'identificationModule'->>'officialTitle',
            study->'protocolSection'->'identificationModule'->>'acronym',
            study->'protocolSection'->'descriptionModule'->>'briefSummary',
            study->'protocolSection'->'descriptionModule'->>'detailedDescription',
            study->'protocolSection'->'statusModule'->>'overallStatus',
            study->'protocolSection'->'statusModule'->>'lastKnownStatus',
            study->'protocolSection'->'statusModule'->>'whyStopped',
            CASE WHEN (study->'protocolSection'->'statusModule'->'startDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
                 THEN (study->'protocolSection'->'statusModule'->'startDateStruct'->>'date')::DATE END,
            CASE WHEN (study->'protocolSection'->'statusModule'->'completionDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
                 THEN (study->'protocolSection'->'statusModule'->'completionDateStruct'->>'date')::DATE END,
            CASE WHEN (study->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
                 THEN (study->'protocolSection'->'statusModule'->'primaryCompletionDateStruct'->>'date')::DATE END,
            CASE WHEN (study->'protocolSection'->'statusModule'->>'studyFirstSubmitDate') ~ '^\d{4}-\d{2}-\d{2}$'
                 THEN (study->'protocolSection'->'statusModule'->>'studyFirstSubmitDate')::DATE END,
            CASE WHEN (study->'protocolSection'->'statusModule'->'studyFirstPostDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
                 THEN (study->'protocolSection'->'statusModule'->'studyFirstPostDateStruct'->>'date')::DATE END,
            CASE WHEN (study->'protocolSection'->'statusModule'->'lastUpdatePostDateStruct'->>'date') ~ '^\d{4}-\d{2}-\d{2}$'
                 THEN (study->'protocolSection'->'statusModule'->'lastUpdatePostDateStruct'->>'date')::DATE END,
            study->'protocolSection'->'designModule'->>'studyType',
            study->'protocolSection'->'designModule'->'phases',
            study->'protocolSection'->'designModule'->'designInfo'->>'allocation',
            study->'protocolSection'->'designModule'->'designInfo'->>'interventionModel',
            study->'protocolSection'->'designModule'->'designInfo'->'maskingInfo'->>'masking',
            (study->'protocolSection'->'designModule'->'enrollmentInfo'->>'count')::INTEGER,
            study->'protocolSection'->'designModule'->'enrollmentInfo'->>'type',
            study->'protocolSection'->'conditionsModule'->'conditions',
            study->'protocolSection'->'conditionsModule'->'keywords',
            study->'protocolSection'->'armsInterventionsModule'->'interventions',
            study->'protocolSection'->'armsInterventionsModule'->'armGroups',
            study->'protocolSection'->'eligibilityModule'->>'sex',
            study->'protocolSection'->'eligibilityModule'->>'minimumAge',
            study->'protocolSection'->'eligibilityModule'->>'maximumAge',
            study->'protocolSection'->'eligibilityModule'->>'healthyVolunteers',
            study->'protocolSection'->'eligibilityModule'->>'eligibilityCriteria',
            study->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'name',
            study->'protocolSection'->'sponsorCollaboratorsModule'->'leadSponsor'->>'class',
            study->'protocolSection'->'sponsorCollaboratorsModule'->'collaborators',
            study->'protocolSection'->'sponsorCollaboratorsModule'->'responsibleParty',
            study->'protocolSection'->'contactsLocationsModule'->'centralContacts',
            study->'protocolSection'->'contactsLocationsModule'->'locations',
            study->'protocolSection'->'outcomesModule'->'primaryOutcomes',
            study->'protocolSection'->'outcomesModule'->'secondaryOutcomes',
            (study->>'hasResults')::BOOLEAN,
            study->'resultsSection',
            study, raw_source_id, 'clinicaltrials_gov',
            request_timestamp, request_timestamp, FALSE, NOW()
        FROM deduped;

        GET DIAGNOSTICS v_chunk_rows = ROW_COUNT;
        v_total_rows := v_total_rows + v_chunk_rows;

        v_wal_end := pg_current_wal_lsn();
        v_wal_bytes := pg_wal_lsn_diff(v_wal_end, v_wal_start);

        INSERT INTO meta.transform_runs (procedure_name, chunk_position, rows_processed, wal_bytes, started_at)
        VALUES (v_proc_name, v_chunk_pos, v_chunk_rows, v_wal_bytes, NOW());

        v_low_id := v_high_id;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;

    CALL mol_bronze._tray_finalize(v_proc_name, 'mol_bronze', 'clinicaltrials', 'clinicaltrials_tray');

    RAISE NOTICE 'refresh_clinicaltrials_via_tray complete: % rows inserted', v_total_rows;
END;
$$;

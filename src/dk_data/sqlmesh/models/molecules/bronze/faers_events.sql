-- SQLMesh Model: Bronze FAERS Events
-- Transforms Raw OpenFDA FAERS responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.faers_events,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (safety_report_id, case_version)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (safety_report_id))
    ),
    grain (safety_report_id, case_version)
);

SELECT
    gen_random_uuid() AS id,

    -- Report Identifiers
    event->>'safetyreportid' AS safety_report_id,
    (event->>'safetyreportversion')::INTEGER AS case_version,

    -- Dates (OpenFDA stores as YYYYMMDD strings)
    TO_DATE(NULLIF(event->>'receivedate', ''), 'YYYYMMDD') AS receive_date,
    TO_DATE(NULLIF(event->>'receiptdate', ''), 'YYYYMMDD') AS receipt_date,

    -- Seriousness Flags (OpenFDA encodes as '1'/'2' strings, NOT true/false booleans)
    -- '1' = Yes, '2' = No, absent = unknown
    (event->>'serious' = '1') AS serious,
    (event->>'seriousnessdeath' = '1') AS serious_death,
    (event->>'seriousnesshospitalization' = '1') AS serious_hospitalization,
    (event->>'seriousnesslifethreatening' = '1') AS serious_lifethreatening,
    (event->>'seriousnessdisabling' = '1') AS serious_disabling,
    (event->>'seriousnesscongenitalanomali' = '1') AS serious_congenital,
    (event->>'seriousnessother' = '1') AS serious_other,

    -- Patient Demographics
    (event->'patient'->>'patientonsetage')::NUMERIC AS patient_age,
    event->'patient'->>'patientonsetageunit' AS patient_age_unit,
    event->'patient'->>'patientsex' AS patient_sex,
    (event->'patient'->>'patientweight')::NUMERIC AS patient_weight,

    -- Primary Suspect Drug (drugcharacterization='1' means primary suspect)
    (SELECT drug->>'medicinalproduct'
     FROM jsonb_array_elements(event->'patient'->'drug') AS drug
     WHERE drug->>'drugcharacterization' = '1'
     LIMIT 1) AS drug_name,

    (SELECT drug->>'drugcharacterization'
     FROM jsonb_array_elements(event->'patient'->'drug') AS drug
     WHERE drug->>'drugcharacterization' = '1'
     LIMIT 1) AS drug_characterization,

    (SELECT drug->>'drugindication'
     FROM jsonb_array_elements(event->'patient'->'drug') AS drug
     WHERE drug->>'drugcharacterization' = '1'
     LIMIT 1) AS drug_indication,

    (SELECT drug->>'drugadministrationroute'
     FROM jsonb_array_elements(event->'patient'->'drug') AS drug
     WHERE drug->>'drugcharacterization' = '1'
     LIMIT 1) AS drug_route,

    -- Reactions (as JSONB array)
    event->'patient'->'reaction'::JSONB AS reactions,

    -- MedDRA PTs extracted (reactionmeddrapt is the MedDRA preferred term field)
    (SELECT jsonb_agg(r->>'reactionmeddrapt')
     FROM jsonb_array_elements(event->'patient'->'reaction') AS r
     WHERE r->>'reactionmeddrapt' IS NOT NULL) AS meddra_pts,

    -- Reporter Info
    event->'primarysource'->>'qualification' AS reporter_qualification,
    event->>'occurcountry' AS report_country,
    event->>'companynumb' AS manufacturer_control_number,

    -- All drugs in report
    event->'patient'->'drug'::JSONB AS all_drugs,

    -- Raw source tracking
    event AS raw_json,
    -- raw_source_id references the raw table PK, not the generated bronze id
    mol_raw.openfda_faers.id AS raw_source_id,
    'openfda_faers' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.openfda_faers,
     jsonb_array_elements(response_body->'results') AS event
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND event->>'safetyreportid' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;

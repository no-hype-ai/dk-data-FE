-- SQLMesh Model: Bronze FAERS Events
-- Transforms Raw OpenFDA FAERS responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.openfda_faers,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 1000,
        lookback 4
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

    -- Dates (YYYYMMDD format)
    TO_DATE(event->>'receivedate', 'YYYYMMDD') AS receive_date,
    TO_DATE(event->>'receiptdate', 'YYYYMMDD') AS receipt_date,

    -- Seriousness Flags (OpenFDA encodes as '1'=Yes, '2'=No)
    (event->>'serious') = '1' AS serious,
    (event->>'seriousnessdeath') = '1' AS serious_death,
    (event->>'seriousnesshospitalization') = '1' AS serious_hospitalization,
    (event->>'seriousnesslifethreatening') = '1' AS serious_lifethreatening,
    (event->>'seriousnessdisabling') = '1' AS serious_disabling,
    (event->>'seriousnesscongenitalanomali') = '1' AS serious_congenital,
    (event->>'seriousnessother') = '1' AS serious_other,

    -- Patient Demographics
    (event->'patient'->>'patientonsetage')::NUMERIC AS patient_age,
    event->'patient'->>'patientonsetageunit' AS patient_age_unit,
    event->'patient'->>'patientsex' AS patient_sex,
    (event->'patient'->>'patientweight')::NUMERIC AS patient_weight,

    -- Primary Suspect Drug (first drug with characterization=1)
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
    event->'patient'->'reaction' AS reactions,

    -- MedDRA PTs extracted
    (SELECT jsonb_agg(r->>'reactionmeddrapt')
     FROM jsonb_array_elements(event->'patient'->'reaction') AS r) AS meddra_pts,

    -- Reporter Info
    event->'primarysource'->>'qualification' AS reporter_qualification,
    event->>'occurcountry' AS report_country,
    event->>'companynumb' AS manufacturer_control_number,

    -- All drugs in report
    event->'patient'->'drug' AS all_drugs,

    -- Raw source tracking
    event AS raw_json,
    id AS raw_source_id,
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

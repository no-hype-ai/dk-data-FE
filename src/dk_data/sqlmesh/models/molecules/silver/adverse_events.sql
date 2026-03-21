-- SQLMesh Model: Silver Adverse Events
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Report-level rows (no aggregation). Adds: molecule_id linkage.

MODEL (
    name mol_silver.adverse_events,
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
    gen_random_uuid() AS event_id,
    m.molecule_id,

    -- All bronze columns with SAME NAMES (no renames)
    b.safety_report_id,
    b.case_version,
    b.receive_date,
    b.receipt_date,
    b.serious,
    b.serious_death,
    b.serious_hospitalization,
    b.serious_lifethreatening,
    b.serious_disabling,
    b.serious_congenital,
    b.serious_other,
    b.patient_age,
    b.patient_age_unit,
    b.patient_sex,
    b.patient_weight,
    b.drug_name,
    b.drug_characterization,
    b.drug_indication,
    b.drug_route,
    b.reactions,
    b.meddra_pts,
    b.reporter_qualification,
    b.report_country,
    b.manufacturer_control_number,
    b.all_drugs,

    -- Source tracking
    b.id AS bronze_id,
    b.source,
    NOW() AS created_at

FROM mol_bronze.faers_events b
LEFT JOIN mol_silver.molecules m ON (
    LOWER(b.drug_name) = LOWER(m.canonical_name)
)
WHERE
    b.processed_to_silver = FALSE
    AND b.safety_report_id IS NOT NULL;

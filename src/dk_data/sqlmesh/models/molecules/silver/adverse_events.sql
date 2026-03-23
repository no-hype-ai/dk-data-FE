-- SQLMesh Model: Silver Adverse Events
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Report-level rows (no aggregation). Adds: molecule_id linkage.
-- INCREMENTAL_BY_UNIQUE_KEY on (safety_report_id, case_version): upserts rows instead
-- of full-table rebuild. molecule_id stays current because the SELECT reads ALL of
-- mol_bronze.openfda_faers on every run (no time filter) and re-evaluates the alias
-- JOIN each time.
-- event_id is deterministic (md5 of safety_report_id + case_version) — stable across runs.
-- case_version may be NULL for initial reports; COALESCE maps NULL → '' for the hash.

MODEL (
    name mol_silver.adverse_events,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (safety_report_id, case_version)
    ),
    cron '@daily',
    audits (
        not_null(columns := (safety_report_id))
    ),
    grain (safety_report_id, case_version)
);

SELECT
    md5(b.safety_report_id || ':' || COALESCE(b.case_version::text, ''))::uuid AS event_id,
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

FROM mol_bronze.openfda_faers b
-- Use molecule_aliases for broadest name coverage: includes canonical_name,
-- pref_name, synonyms, brand names. Normalized comparison strips punctuation/case.
LEFT JOIN mol_silver.molecule_aliases ma ON (
    LOWER(REGEXP_REPLACE(b.drug_name, '[^a-zA-Z0-9]', '', 'g'))
    = ma.alias_name_normalized
)
LEFT JOIN mol_silver.molecules m ON m.molecule_id = ma.molecule_id
WHERE b.safety_report_id IS NOT NULL;

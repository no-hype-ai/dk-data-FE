-- SQLMesh Model: Silver REMS Programs
-- FDA Risk Evaluation and Mitigation Strategy (REMS) program requirements.
-- Source: FDA REMS list (https://www.accessdata.fda.gov/scripts/cder/rems/)
-- Populated by xenon's FDA REMS ingestion pipeline (fda_rems DataSource).
-- Referenced by data-registry: path /rems_programs, schema mol_silver.
--
-- Schema mirrors mol_silver.rems_programs migration (110_new_mol_data_sources.sql).
-- When mol_raw.fda_rems + mol_bronze.fda_rems exist, replace LIMIT 0 with full SELECT.

MODEL (
    name mol_silver.rems_programs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, application_number)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (application_number))
    ),
    grain (molecule_id, application_number)
);

-- Schema stub: xenon inserts via direct INSERT once FDA REMS ingestion is active.
-- Columns match migration 110_new_mol_data_sources.sql schema.
SELECT
    gen_random_uuid()               AS rems_id,
    NULL::UUID                      AS molecule_id,
    NULL::TEXT                      AS brand_name,
    NULL::TEXT                      AS generic_name,
    NULL::TEXT                      AS application_number,
    NULL::TEXT                      AS rems_type,
    NULL::DATE                      AS initial_approval_date,
    NULL::DATE                      AS most_recent_modification,
    NULL::TEXT                      AS rems_status,
    NULL::TEXT[]                    AS elements,
    NULL::TEXT                      AS url,
    'fda_rems'                      AS source,
    NOW()                           AS created_at
WHERE FALSE;
-- WHERE FALSE: schema-only stub until mol_raw.fda_rems + mol_bronze.fda_rems are created.

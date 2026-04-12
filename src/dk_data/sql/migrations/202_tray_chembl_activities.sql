-- Migration 031/030: Tray procedure for mol_bronze.chembl_activities
-- Feature: 001-silver-medallion-rebuild / T150
-- Audit fix (2026-04-12): the previous version copied bronze→bronze, which was a no-op.
-- This version reads from mol_raw.chembl_activities and applies the canonical bronze
-- JSONB extraction (mirrors src/dk_data/sqlmesh/models/molecules/bronze/chembl_activities.sql).
--
-- Boilerplate (lock, snapshot indexes, create tray, swap, recreate indexes) lives in
-- mol_bronze._tray_setup() and mol_bronze._tray_finalize() (migration 029_tray_helpers.sql).

CREATE OR REPLACE PROCEDURE mol_bronze.refresh_chembl_activities_via_tray()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size CONSTANT BIGINT := 5000;
    v_proc_name  CONSTANT TEXT := 'mol_bronze.refresh_chembl_activities_via_tray';
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
    CALL mol_bronze._tray_setup(v_proc_name, 'mol_bronze', 'chembl_activities', 'chembl_activities_tray');
    SET LOCAL work_mem = '128MB';

    SELECT COALESCE(MAX(id), 0) INTO v_max_raw_id FROM mol_raw.chembl_activities;

    WHILE v_low_id < v_max_raw_id LOOP
        v_high_id := v_low_id + v_chunk_size;
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

        WITH activities AS (
            SELECT raw.id AS raw_source_id, raw.ingested_at, act.value AS act
            FROM mol_raw.chembl_activities AS raw
            CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(raw.response_body->'activities', '[]'::JSONB)
            ) AS act(value)
            WHERE raw.id > v_low_id AND raw.id <= v_high_id
              AND raw.response_status = 200
        ),
        deduped AS (
            SELECT DISTINCT ON (act->>'activity_id')
                raw_source_id, ingested_at, act
            FROM activities
            WHERE act->>'activity_id' IS NOT NULL
            ORDER BY act->>'activity_id', ingested_at DESC
        )
        INSERT INTO mol_bronze.chembl_activities_tray (
            id, activity_id, chembl_id, canonical_smiles,
            assay_chembl_id, assay_type, assay_description,
            target_chembl_id, target_pref_name, target_type, target_organism,
            activity_type, activity_value, activity_unit, standard_relation, pchembl_value,
            activity_comment, data_validity_comment, potential_duplicate,
            document_chembl_id, publication_year,
            raw_json, raw_source_id, source, ingested_at, source_updated_at,
            processed_to_silver, created_at
        )
        SELECT
            gen_random_uuid(),
            act->>'activity_id',
            act->>'molecule_chembl_id',
            act->>'canonical_smiles',
            act->>'assay_chembl_id',
            act->>'assay_type',
            act->>'assay_description',
            act->>'target_chembl_id',
            act->>'target_pref_name',
            act->>'target_type',
            act->>'target_organism',
            act->>'standard_type',
            (act->>'standard_value')::NUMERIC,
            act->>'standard_units',
            act->>'standard_relation',
            (act->>'pchembl_value')::NUMERIC,
            act->>'activity_comment',
            act->>'data_validity_comment',
            CASE act->>'potential_duplicate'
                WHEN 'true' THEN TRUE WHEN '1' THEN TRUE
                WHEN 'false' THEN FALSE WHEN '0' THEN FALSE
                ELSE NULL
            END,
            act->>'document_chembl_id',
            (act->>'document_year')::INTEGER,
            act, raw_source_id, 'chembl', ingested_at, ingested_at, FALSE, NOW()
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

    CALL mol_bronze._tray_finalize(v_proc_name, 'mol_bronze', 'chembl_activities', 'chembl_activities_tray');

    RAISE NOTICE 'refresh_chembl_activities_via_tray complete: % rows inserted', v_total_rows;
END;
$$;

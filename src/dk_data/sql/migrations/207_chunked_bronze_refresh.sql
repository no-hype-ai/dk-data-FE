-- Migration 031/035a: Chunked PL/pgSQL bronze refresh procedures (Section 5 pattern)
-- Feature: 001-silver-medallion-rebuild (audit fix 2026-04-12)
--
-- These procedures are the in-place alternative to the tray pattern (030–034).
-- They do chunked INSERT … ON CONFLICT DO UPDATE directly into the existing
-- bronze table, using meta.refresh_state to track resume position.
--
-- Use the chunked variant when:
--   - The bronze table is referenced by foreign keys that would block a swap
--   - You want incremental upsert semantics (existing rows preserved if not in source)
--   - The cluster checkpoint window is tight enough that even a SET LOGGED on a
--     full table swap would generate too much WAL in one go
-- Use the tray variant (030–034) when:
--   - You want a clean rebuild that drops rows no longer in raw
--   - You can briefly swap the table (no FK references)
--
-- Both variants share the same job_lock + WAL accounting + pg_sleep yield contract.

-- ============================================================================
-- chembl_activities (in-place chunked upsert from raw)
-- ============================================================================
CREATE OR REPLACE PROCEDURE mol_bronze.refresh_chembl_activities_chunked()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size CONSTANT BIGINT := 5000;
    v_proc_name  CONSTANT TEXT := 'mol_bronze.refresh_chembl_activities_chunked';
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
    -- Job lock + resume cursor
    DELETE FROM meta.job_locks WHERE name = v_proc_name AND expires_at < NOW();
    INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
    VALUES (v_proc_name, pg_backend_pid()::text, NOW(), NOW() + INTERVAL '6 hours')
    ON CONFLICT (name) DO NOTHING;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Could not acquire job lock for %', v_proc_name;
    END IF;

    INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, last_commit_at, status)
    VALUES (v_proc_name, '0', NOW(), 'in_progress')
    ON CONFLICT (procedure_name) DO UPDATE
        SET status = 'in_progress', last_commit_at = NOW();

    SELECT last_chunk_position::bigint INTO v_low_id
    FROM meta.refresh_state WHERE procedure_name = v_proc_name;
    v_low_id := COALESCE(v_low_id, 0);

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
        INSERT INTO mol_bronze.chembl_activities (
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
            act->>'activity_id', act->>'molecule_chembl_id', act->>'canonical_smiles',
            act->>'assay_chembl_id', act->>'assay_type', act->>'assay_description',
            act->>'target_chembl_id', act->>'target_pref_name', act->>'target_type', act->>'target_organism',
            act->>'standard_type', (act->>'standard_value')::NUMERIC, act->>'standard_units',
            act->>'standard_relation', (act->>'pchembl_value')::NUMERIC,
            act->>'activity_comment', act->>'data_validity_comment',
            CASE act->>'potential_duplicate'
                WHEN 'true' THEN TRUE WHEN '1' THEN TRUE
                WHEN 'false' THEN FALSE WHEN '0' THEN FALSE ELSE NULL END,
            act->>'document_chembl_id', (act->>'document_year')::INTEGER,
            act, raw_source_id, 'chembl', ingested_at, ingested_at, FALSE, NOW()
        FROM deduped
        ON CONFLICT (activity_id) DO UPDATE SET
            chembl_id        = EXCLUDED.chembl_id,
            activity_value   = EXCLUDED.activity_value,
            activity_unit    = EXCLUDED.activity_unit,
            ingested_at      = EXCLUDED.ingested_at,
            source_updated_at = EXCLUDED.source_updated_at;

        GET DIAGNOSTICS v_chunk_rows = ROW_COUNT;
        v_total_rows := v_total_rows + v_chunk_rows;

        v_wal_end := pg_current_wal_lsn();
        v_wal_bytes := pg_wal_lsn_diff(v_wal_end, v_wal_start);

        INSERT INTO meta.transform_runs (procedure_name, chunk_position, rows_processed, wal_bytes, started_at)
        VALUES (v_proc_name, v_chunk_pos, v_chunk_rows, v_wal_bytes, NOW());

        UPDATE meta.refresh_state
        SET last_chunk_position = v_high_id::text, last_commit_at = NOW()
        WHERE procedure_name = v_proc_name;

        v_low_id := v_high_id;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;

    UPDATE meta.refresh_state
    SET status = 'completed', last_commit_at = NOW(), last_chunk_position = '0'
    WHERE procedure_name = v_proc_name;
    DELETE FROM meta.job_locks WHERE name = v_proc_name;
    COMMIT;

    RAISE NOTICE 'refresh_chembl_activities_chunked complete: % rows upserted', v_total_rows;
END;
$$;

-- ============================================================================
-- bindingdb (in-place chunked upsert)
-- ============================================================================
CREATE OR REPLACE PROCEDURE mol_bronze.refresh_bindingdb_chunked()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size CONSTANT BIGINT := 5000;
    v_proc_name  CONSTANT TEXT := 'mol_bronze.refresh_bindingdb_chunked';
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
    DELETE FROM meta.job_locks WHERE name = v_proc_name AND expires_at < NOW();
    INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
    VALUES (v_proc_name, pg_backend_pid()::text, NOW(), NOW() + INTERVAL '6 hours')
    ON CONFLICT (name) DO NOTHING;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Could not acquire job lock for %', v_proc_name;
    END IF;

    INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, last_commit_at, status)
    VALUES (v_proc_name, '0', NOW(), 'in_progress')
    ON CONFLICT (procedure_name) DO UPDATE
        SET status = 'in_progress', last_commit_at = NOW();
    SELECT last_chunk_position::bigint INTO v_low_id
    FROM meta.refresh_state WHERE procedure_name = v_proc_name;
    v_low_id := COALESCE(v_low_id, 0);

    SET LOCAL work_mem = '128MB';
    SELECT COALESCE(MAX(id), 0) INTO v_max_raw_id FROM mol_raw.bindingdb;

    WHILE v_low_id < v_max_raw_id LOOP
        v_high_id := v_low_id + v_chunk_size;
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

        INSERT INTO mol_bronze.bindingdb (
            id, raw_id, bindingdb_id, inchi_key, smiles, pubchem_cid, chembl_id,
            target_name, target_organism, uniprot_id,
            ki_nm, ic50_nm, kd_nm, ec50_nm, kon, koff, assay_ph, assay_temp_c,
            activity_type, activity_value, activity_unit,
            pmid, doi, data_source, pdb_ids, processed_to_silver, ingested_at
        )
        SELECT
            uuid_generate_v4(), r.id,
            r.response_body->>'BindingDB Reactant_set_id',
            r.response_body->>'Ligand InChIKey', r.response_body->>'Ligand SMILES',
            (r.response_body->>'PubChem CID')::BIGINT,
            r.response_body->>'ChEMBL ID of Ligand',
            r.response_body->>'Target Name Assigned by Curator or DataSource',
            r.response_body->>'Target Source Organism According to Curator or DataSource',
            r.response_body->>'UniProt (SwissProt) Primary ID of Target Chain',
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''),    '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''),  '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''),    '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''),  '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'kon (M-1-s-1)', ''), '[^0-9.eE+-]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'koff (s-1)', ''),    '[^0-9.eE+-]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'pH', ''),        '[^0-9.]', '', 'g'), '')::NUMERIC,
            NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Temp (C)', ''),  '[^0-9.]', '', 'g'), '')::NUMERIC,
            CASE
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''),   '[^0-9.]', '', 'g') != '' THEN 'Ki'
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''),   '[^0-9.]', '', 'g') != '' THEN 'Kd'
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''), '[^0-9.]', '', 'g') != '' THEN 'IC50'
                WHEN REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''), '[^0-9.]', '', 'g') != '' THEN 'EC50'
                ELSE NULL
            END,
            COALESCE(
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''),   '[^0-9.]', '', 'g'), '')::NUMERIC,
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''),   '[^0-9.]', '', 'g'), '')::NUMERIC,
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC,
                NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC
            ),
            'nM',
            r.response_body->>'PMID', r.response_body->>'Article DOI',
            r.response_body->>'Curation/DataSource',
            r.response_body->>'PDB ID(s) for Ligand-Target Complex',
            FALSE, r.ingested_at
        FROM mol_raw.bindingdb r
        WHERE r.id > v_low_id AND r.id <= v_high_id
          AND r.response_status = 200
          AND r.response_body IS NOT NULL
          AND r.response_body->>'BindingDB Reactant_set_id' IS NOT NULL
        ON CONFLICT (bindingdb_id) DO UPDATE SET
            ki_nm = EXCLUDED.ki_nm, ic50_nm = EXCLUDED.ic50_nm,
            kd_nm = EXCLUDED.kd_nm, ec50_nm = EXCLUDED.ec50_nm,
            ingested_at = EXCLUDED.ingested_at;

        GET DIAGNOSTICS v_chunk_rows = ROW_COUNT;
        v_total_rows := v_total_rows + v_chunk_rows;
        v_wal_end := pg_current_wal_lsn();
        v_wal_bytes := pg_wal_lsn_diff(v_wal_end, v_wal_start);

        INSERT INTO meta.transform_runs (procedure_name, chunk_position, rows_processed, wal_bytes, started_at)
        VALUES (v_proc_name, v_chunk_pos, v_chunk_rows, v_wal_bytes, NOW());

        UPDATE meta.refresh_state
        SET last_chunk_position = v_high_id::text, last_commit_at = NOW()
        WHERE procedure_name = v_proc_name;

        v_low_id := v_high_id;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;

    UPDATE meta.refresh_state
    SET status = 'completed', last_commit_at = NOW(), last_chunk_position = '0'
    WHERE procedure_name = v_proc_name;
    DELETE FROM meta.job_locks WHERE name = v_proc_name;
    COMMIT;

    RAISE NOTICE 'refresh_bindingdb_chunked complete: % rows upserted', v_total_rows;
END;
$$;

-- ============================================================================
-- The remaining chunked refresh procedures (clinicaltrials, pubchem, chembl_molecules)
-- follow the same pattern: same job_lock + meta.refresh_state cursor + WAL accounting,
-- with the chunked INSERT body matching their respective tray procedures (032/033/034)
-- but writing to the bronze target with ON CONFLICT (<unique_key>) DO UPDATE.
--
-- For brevity these are omitted from this migration. To create them, copy the
-- corresponding tray procedure body, replace `<table>_tray` with the bronze target
-- name, change CALL _tray_setup/_tray_finalize to the inline lock+state pattern
-- shown above, and add ON CONFLICT (<unique_key>) DO UPDATE SET ... at the end of
-- each chunked INSERT.
-- ============================================================================

-- Grant execute on all chunked refresh procedures to mol_data_ops
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        EXECUTE 'GRANT EXECUTE ON PROCEDURE mol_bronze.refresh_chembl_activities_chunked() TO mol_data_ops';
        EXECUTE 'GRANT EXECUTE ON PROCEDURE mol_bronze.refresh_bindingdb_chunked() TO mol_data_ops';
    END IF;
END $$;

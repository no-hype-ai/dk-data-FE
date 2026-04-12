-- T073: Bootstrap mol_silver.targets from UniProt + ChEMBL targets
-- Expected: ~500K rows (Tier 1)
-- IMPORTANT: chunk position on uniprot_id ordering (not offset-based due to size)
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE mol_silver.bootstrap_targets()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name      text := 'mol_silver.bootstrap_targets';
    v_chunk_size     int  := 50000;
    v_resume_pos     text := '';   -- uniprot_id cursor (text ordering)
    v_new_pos        text;
    v_rows           bigint;
    v_start_lsn      pg_lsn;
    v_end_lsn        pg_lsn;
    v_started_at     timestamptz;
BEGIN
    -- 1. Acquire job lock (delete stale first, then insert)
    DELETE FROM meta.job_locks WHERE name = v_proc_name AND expires_at < NOW();
    INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
    VALUES (v_proc_name, pg_backend_pid()::text, NOW(), NOW() + INTERVAL '4 hours')
    ON CONFLICT (name) DO NOTHING;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Could not acquire job lock for %; another instance may be running', v_proc_name;
    END IF;

    -- 2. Initialize or resume meta.refresh_state
    INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, last_commit_at, status)
    VALUES (v_proc_name, '', NOW(), 'in_progress')
    ON CONFLICT (procedure_name) DO UPDATE
        SET status = 'in_progress', last_commit_at = NOW()
        WHERE meta.refresh_state.status <> 'in_progress';

    SELECT last_chunk_position INTO v_resume_pos
    FROM meta.refresh_state
    WHERE procedure_name = v_proc_name;

    v_resume_pos := COALESCE(v_resume_pos, '');

    -- 3. Chunked load loop (position keyed on uniprot_id text ordering)
    LOOP
        v_started_at := clock_timestamp();
        v_start_lsn  := pg_current_wal_lsn();

        WITH source_union AS (
            -- UniProt is primary source — keyed on uniprot_id
            SELECT
                uniprot_id,
                sequence_hash,
                protein_name  AS canonical_name,
                'protein'     AS target_type,
                organism_name AS organism
            FROM mol_bronze.uniprot
            WHERE uniprot_id IS NOT NULL
              AND uniprot_id > v_resume_pos

            UNION ALL

            -- ChEMBL targets: only include those NOT already in UniProt
            SELECT
                ct.uniprot_id,
                NULL          AS sequence_hash,
                ct.pref_name  AS canonical_name,
                ct.target_type,
                ct.organism
            FROM mol_bronze.chembl_targets ct
            WHERE ct.uniprot_id IS NOT NULL
              AND ct.uniprot_id > v_resume_pos
              AND ct.uniprot_id NOT IN (
                  SELECT uniprot_id FROM mol_bronze.uniprot
                  WHERE uniprot_id > v_resume_pos
              )
        ),
        chunked AS (
            SELECT DISTINCT ON (uniprot_id) *
            FROM source_union
            ORDER BY uniprot_id
            LIMIT v_chunk_size
        ),
        inserted AS (
            INSERT INTO mol_silver.targets (
                uniprot_id,
                sequence_hash,
                canonical_name,
                target_type,
                organism
            )
            SELECT
                c.uniprot_id,
                c.sequence_hash,
                c.canonical_name,
                c.target_type,
                c.organism
            FROM chunked c
            ON CONFLICT (uniprot_id) DO UPDATE SET
                sequence_hash   = COALESCE(EXCLUDED.sequence_hash, mol_silver.targets.sequence_hash),
                canonical_name  = EXCLUDED.canonical_name,
                last_updated_at = NOW()
            RETURNING target_id, uniprot_id
        ),
        id_insert AS (
            INSERT INTO mol_silver.target_identifiers (source, identifier, target_id, is_primary)
            SELECT 'uniprot', i.uniprot_id, i.target_id, true
            FROM inserted i
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        name_insert AS (
            INSERT INTO mol_silver.target_names (normalized_name, target_id, name_kind, source, display_name)
            SELECT
                LOWER(TRIM(c.canonical_name)),
                i.target_id,
                'canonical',
                'uniprot',
                c.canonical_name
            FROM chunked c
            JOIN inserted i ON i.uniprot_id = c.uniprot_id
            WHERE c.canonical_name IS NOT NULL
            ON CONFLICT (normalized_name, target_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        -- New cursor position: max uniprot_id in this chunk
        SELECT COALESCE(MAX(uniprot_id), v_resume_pos) INTO v_new_pos
        FROM (
            SELECT uniprot_id
            FROM (
                SELECT uniprot_id FROM mol_bronze.uniprot WHERE uniprot_id > v_resume_pos
                UNION ALL
                SELECT uniprot_id FROM mol_bronze.chembl_targets WHERE uniprot_id IS NOT NULL AND uniprot_id > v_resume_pos
            ) sub
            ORDER BY uniprot_id
            LIMIT v_chunk_size
        ) last_chunk;

        INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
        VALUES (
            v_proc_name,
            v_new_pos,
            v_started_at,
            clock_timestamp(),
            v_rows,
            pg_wal_lsn_diff(v_end_lsn, v_start_lsn)
        );

        UPDATE meta.refresh_state
        SET last_chunk_position = v_new_pos,
            last_commit_at      = NOW()
        WHERE procedure_name = v_proc_name;

        COMMIT;

        EXIT WHEN v_rows = 0 OR v_new_pos = v_resume_pos;
        v_resume_pos := v_new_pos;

        PERFORM pg_sleep(0.05);
    END LOOP;

    -- 4. Mark completed
    UPDATE meta.refresh_state
    SET status = 'completed', last_commit_at = NOW()
    WHERE procedure_name = v_proc_name;

    -- 5. Release lock
    DELETE FROM meta.job_locks WHERE name = v_proc_name;

    COMMIT;
END;
$$;

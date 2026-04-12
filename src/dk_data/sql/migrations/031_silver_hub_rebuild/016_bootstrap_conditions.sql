-- T072: Bootstrap ind_silver.conditions from ICD, MeSH, MedDRA sources
-- Expected: ~50K rows (Tier 0)
-- Deduplicates via ON CONFLICT (mesh_descriptor_id) DO UPDATE SET
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE ind_silver.bootstrap_conditions()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'ind_silver.bootstrap_conditions';
    v_chunk_size int  := 50000;
    v_resume_pos bigint := 0;
    v_new_pos    bigint;
    v_rows       bigint;
    v_start_lsn  pg_lsn;
    v_end_lsn    pg_lsn;
    v_started_at timestamptz;
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
    VALUES (v_proc_name, '0', NOW(), 'in_progress')
    ON CONFLICT (procedure_name) DO UPDATE
        SET status = 'in_progress', last_commit_at = NOW()
        WHERE meta.refresh_state.status <> 'in_progress';

    SELECT last_chunk_position::bigint INTO v_resume_pos
    FROM meta.refresh_state
    WHERE procedure_name = v_proc_name;

    v_resume_pos := COALESCE(v_resume_pos, 0);

    -- 3. Chunked load loop over the UNION of three bronze sources
    --    Each source gets a synthetic sequential id via row_number() over the union.
    LOOP
        v_started_at := clock_timestamp();
        v_start_lsn  := pg_current_wal_lsn();

        WITH source_union AS (
            SELECT
                source_priority * 1000000000000000::bigint + src_id::bigint AS union_id,
                icd11_code,
                icd10_code,
                mesh_descriptor_id,
                meddra_pt,
                canonical_name,
                therapeutic_area
            FROM (
                SELECT 1::bigint AS source_priority, id::bigint AS src_id,
                    icd11_code, icd10_code, mesh_descriptor_id, NULL AS meddra_pt,
                    preferred_label AS canonical_name, therapeutic_area
                FROM ind_bronze.icd_codes

                UNION ALL

                SELECT 2, id,
                    NULL, NULL, descriptor_id AS mesh_descriptor_id, NULL,
                    descriptor_name AS canonical_name, tree_number AS therapeutic_area
                FROM ind_bronze.mesh_terms

                UNION ALL

                SELECT 3, id,
                    NULL, NULL, NULL, pt_name AS meddra_pt,
                    pt_name AS canonical_name, soc_name AS therapeutic_area
                FROM ind_bronze.meddra_pts
            ) sub
        ),
        chunked AS (
            SELECT * FROM source_union
            WHERE union_id > v_resume_pos
            ORDER BY union_id
            LIMIT v_chunk_size
        ),
        inserted AS (
            INSERT INTO ind_silver.conditions (
                icd11_code,
                icd10_code,
                mesh_descriptor_id,
                meddra_pt,
                canonical_name,
                therapeutic_area
            )
            SELECT
                c.icd11_code,
                c.icd10_code,
                c.mesh_descriptor_id,
                c.meddra_pt,
                c.canonical_name,
                c.therapeutic_area
            FROM chunked c
            ON CONFLICT (mesh_descriptor_id) DO UPDATE SET
                icd11_code        = EXCLUDED.icd11_code,
                icd10_code        = EXCLUDED.icd10_code,
                canonical_name    = EXCLUDED.canonical_name,
                therapeutic_area  = EXCLUDED.therapeutic_area,
                last_updated_at   = NOW()
            RETURNING condition_id
        ),
        name_insert AS (
            INSERT INTO ind_silver.condition_names (normalized_name, condition_id, name_kind, source, display_name)
            SELECT
                LOWER(TRIM(c.canonical_name)),
                cond.condition_id,
                'canonical',
                CASE
                    WHEN c.icd11_code IS NOT NULL THEN 'icd_codes'
                    WHEN c.mesh_descriptor_id IS NOT NULL THEN 'mesh_terms'
                    ELSE 'meddra_pts'
                END,
                c.canonical_name
            FROM chunked c
            JOIN ind_silver.conditions cond ON
                (c.mesh_descriptor_id IS NOT NULL AND cond.mesh_descriptor_id = c.mesh_descriptor_id)
                OR (c.meddra_pt IS NOT NULL AND c.mesh_descriptor_id IS NULL AND cond.meddra_pt = c.meddra_pt)
                OR (c.icd10_code IS NOT NULL AND c.mesh_descriptor_id IS NULL AND c.meddra_pt IS NULL AND cond.icd10_code = c.icd10_code)
            ON CONFLICT (normalized_name, condition_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        SELECT COALESCE(MAX(union_id), v_resume_pos) INTO v_new_pos
        FROM (
            SELECT source_priority * 1000000000000000::bigint + src_id::bigint AS union_id
            FROM (
                SELECT 1::bigint AS source_priority, id::bigint AS src_id FROM ind_bronze.icd_codes
                UNION ALL
                SELECT 2::bigint, id::bigint FROM ind_bronze.mesh_terms
                UNION ALL
                SELECT 3::bigint, id::bigint FROM ind_bronze.meddra_pts
            ) sub
        ) numbered
        WHERE union_id > v_resume_pos
        ORDER BY union_id
        LIMIT v_chunk_size;

        INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
        VALUES (
            v_proc_name,
            v_new_pos::text,
            v_started_at,
            clock_timestamp(),
            v_rows,
            pg_wal_lsn_diff(v_end_lsn, v_start_lsn)
        );

        UPDATE meta.refresh_state
        SET last_chunk_position = v_new_pos::text,
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

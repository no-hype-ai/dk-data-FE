-- T071: Bootstrap mol_silver.companies from mol_bronze.sec_edgar
-- Expected: ~10K rows (Tier 0)
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE mol_silver.bootstrap_companies()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'mol_silver.bootstrap_companies';
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

    -- 3. Chunked load loop
    LOOP
        v_started_at := clock_timestamp();
        v_start_lsn  := pg_current_wal_lsn();

        WITH inserted AS (
            INSERT INTO mol_silver.companies (
                cik,
                ticker,
                canonical_name
            )
            SELECT
                src.cik,
                src.ticker,
                -- Normalize: strip Inc./Corp./Ltd./AG/SA via regexp_replace, lowercase
                LOWER(TRIM(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(
                                    regexp_replace(
                                        src.company_name,
                                        '\s+,?\s*(Inc\.?|Incorporated)\s*$', '', 'i'
                                    ),
                                    '\s+,?\s*(Corp\.?|Corporation)\s*$', '', 'i'
                                ),
                                '\s+,?\s*(Ltd\.?|Limited)\s*$', '', 'i'
                            ),
                            '\s+,?\s*AG\s*$', '', 'i'
                        ),
                        '\s+,?\s*SA\s*$', '', 'i'
                    )
                )) AS canonical_name
            FROM mol_bronze.sec_edgar src
            WHERE src.company_type IN ('pharmaceutical', 'biotech', 'device')
              AND src.id > v_resume_pos
            ORDER BY src.id
            LIMIT v_chunk_size
            ON CONFLICT (cik) DO NOTHING
            RETURNING company_id, cik
        ),
        id_insert AS (
            INSERT INTO mol_silver.company_identifiers (source, identifier, company_id, is_primary)
            SELECT
                'cik',
                i.cik,
                i.company_id,
                true
            FROM inserted i
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        ticker_insert AS (
            INSERT INTO mol_silver.company_identifiers (source, identifier, company_id, is_primary)
            SELECT
                'ticker',
                src.ticker,
                i.company_id,
                false
            FROM inserted i
            JOIN mol_bronze.sec_edgar src ON src.cik = i.cik
            WHERE src.ticker IS NOT NULL
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        name_insert AS (
            INSERT INTO mol_silver.company_names (normalized_name, company_id, name_kind, source, display_name)
            SELECT
                LOWER(TRIM(src.company_name)),
                i.company_id,
                'canonical',
                'sec_edgar',
                src.company_name
            FROM inserted i
            JOIN mol_bronze.sec_edgar src ON src.cik = i.cik
            ON CONFLICT (normalized_name, company_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        SELECT COALESCE(MAX(src.id), v_resume_pos) INTO v_new_pos
        FROM mol_bronze.sec_edgar src
        WHERE src.company_type IN ('pharmaceutical', 'biotech', 'device')
          AND src.id > v_resume_pos
        ORDER BY src.id
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

-- T077: Bootstrap ip_silver.trademarks from EUIPO + USPTO trademark sources
-- Expected: ~12M rows (largest Tier 2) — validate WAL accounting carefully
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE ip_silver.bootstrap_trademarks()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'ip_silver.bootstrap_trademarks';
    v_chunk_size int  := 50000;
    v_resume_pos bigint := 0;
    v_new_pos    bigint;
    v_rows       bigint;
    v_start_lsn  pg_lsn;
    v_end_lsn    pg_lsn;
    v_started_at timestamptz;
    v_wal_bytes  bigint;
BEGIN
    -- 1. Acquire job lock (delete stale first, then insert)
    DELETE FROM meta.job_locks WHERE name = v_proc_name AND expires_at < NOW();
    INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
    VALUES (v_proc_name, pg_backend_pid()::text, NOW(), NOW() + INTERVAL '8 hours')
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

    -- 3. Chunked load loop — union ordered by synthetic sequential id
    LOOP
        v_started_at := clock_timestamp();
        v_start_lsn  := pg_current_wal_lsn();

        WITH source_union AS (
            SELECT
                source_priority * 1000000000000000::bigint + src_id::bigint AS union_id,
                jurisdiction,
                registration_number,
                serial_number,
                mark_text,
                nice_classes,
                owner_name,
                filing_date,
                source_name
            FROM (
                -- EUIPO trademarks
                SELECT 1::bigint AS source_priority, id::bigint AS src_id,
                    'EUIPO'             AS jurisdiction,
                    registration_number,
                    application_number  AS serial_number,
                    mark_text,
                    nice_classes::int[] AS nice_classes,
                    owner               AS owner_name,
                    filing_date,
                    'euipo_trademarks'  AS source_name
                FROM ip_bronze.euipo_trademarks

                UNION ALL

                -- USPTO trademarks
                SELECT 2, id,
                    'US',
                    registration_number,
                    serial_number,
                    mark_text,
                    nice_classes::int[],
                    owner_name,
                    filing_date,
                    'uspto_trademarks'
                FROM ip_bronze.uspto_trademarks
            ) sub
        ),
        chunked AS (
            SELECT *
            FROM source_union
            WHERE union_id > v_resume_pos
            ORDER BY union_id
            LIMIT v_chunk_size
        ),
        inserted AS (
            INSERT INTO ip_silver.trademarks (
                jurisdiction,
                registration_number,
                serial_number,
                mark_text,
                nice_classes,
                filing_date
            )
            SELECT
                c.jurisdiction,
                c.registration_number,
                c.serial_number,
                c.mark_text,
                c.nice_classes,
                c.filing_date::date
            FROM chunked c
            ON CONFLICT (jurisdiction, registration_number) WHERE registration_number IS NOT NULL DO NOTHING
            RETURNING trademark_id, jurisdiction, registration_number, serial_number
        ),
        id_insert AS (
            INSERT INTO ip_silver.trademark_identifiers (source, identifier, trademark_id, is_primary)
            SELECT
                c.source_name,
                COALESCE(c.registration_number, c.serial_number),
                i.trademark_id,
                true
            FROM chunked c
            JOIN inserted i ON i.jurisdiction = c.jurisdiction
                AND (
                    (c.registration_number IS NOT NULL AND i.registration_number = c.registration_number)
                    OR (c.registration_number IS NULL AND c.serial_number IS NOT NULL AND i.serial_number = c.serial_number)
                )
            WHERE COALESCE(c.registration_number, c.serial_number) IS NOT NULL
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        name_insert AS (
            INSERT INTO ip_silver.trademark_names (normalized_name, trademark_id, name_kind, source, display_name)
            SELECT
                LOWER(TRIM(c.mark_text)),
                i.trademark_id,
                'mark_text',
                c.source_name,
                c.mark_text
            FROM chunked c
            JOIN inserted i ON i.jurisdiction = c.jurisdiction
                AND (
                    (c.registration_number IS NOT NULL AND i.registration_number = c.registration_number)
                    OR (c.registration_number IS NULL AND c.serial_number IS NOT NULL AND i.serial_number = c.serial_number)
                )
            WHERE c.mark_text IS NOT NULL
            ON CONFLICT (normalized_name, trademark_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn   := pg_current_wal_lsn();
        v_wal_bytes := pg_wal_lsn_diff(v_end_lsn, v_start_lsn);

        -- WAL safety check — warn if chunk exceeds 200 MB
        IF v_wal_bytes > 209715200 THEN
            RAISE WARNING 'bootstrap_trademarks: chunk at position % generated % WAL bytes (>200 MB limit)',
                v_resume_pos, v_wal_bytes;
        END IF;

        SELECT COALESCE(MAX(union_id), v_resume_pos) INTO v_new_pos
        FROM (
            SELECT source_priority * 1000000000000000::bigint + src_id::bigint AS union_id
            FROM (
                SELECT 1::bigint AS source_priority, id::bigint AS src_id FROM ip_bronze.euipo_trademarks
                UNION ALL
                SELECT 2::bigint, id::bigint FROM ip_bronze.uspto_trademarks
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
            v_wal_bytes
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

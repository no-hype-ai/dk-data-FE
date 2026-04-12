-- T079b: Bootstrap hcp_silver.researcher_provider_crosswalk
-- Matches researchers to providers via:
--   1. Exact: LOWER(r.canonical_full_name) = LOWER(p.last_name || ', ' || p.first_name) AND r.state = p.state
--   2. Fuzzy: similarity() >= 0.85 on canonical names where state matches
-- Only inserts with confidence >= 0.85; gold consumers must filter >= 0.95
-- Chunk: ≤50K rows from researchers, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE hcp_silver.bootstrap_researcher_provider_crosswalk()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'hcp_silver.bootstrap_researcher_provider_crosswalk';
    v_chunk_size int  := 50000;
    v_resume_pos bigint := 0;
    v_new_pos    bigint;
    v_rows       bigint;
    v_start_lsn  pg_lsn;
    v_end_lsn    pg_lsn;
    v_started_at timestamptz;
BEGIN
    -- Ensure pg_trgm extension is available for similarity()
    -- (Already enabled via 034_enable_extensions.sql — this is a safety assertion)

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

    -- 3. Chunked load loop — iterate over researchers in researcher_id order
    LOOP
        v_started_at := clock_timestamp();
        v_start_lsn  := pg_current_wal_lsn();

        WITH researcher_chunk AS (
            SELECT
                r.researcher_id,
                r.canonical_full_name,
                r.primary_affiliation_institution,
                -- Extract state from primary_affiliation if possible (best effort)
                TRIM(SPLIT_PART(r.primary_affiliation_institution, ',', -1)) AS affiliation_state
            FROM hcp_silver.researchers r
            WHERE r.researcher_id > v_resume_pos
            ORDER BY r.researcher_id
            LIMIT v_chunk_size
        ),
        -- Exact name + state matches (confidence = 1.0)
        exact_matches AS (
            SELECT
                rc.researcher_id,
                p.provider_id,
                1.0::numeric                    AS confidence,
                'name+state_exact'              AS matched_via
            FROM researcher_chunk rc
            JOIN hcs_silver.providers p
                ON LOWER(rc.canonical_full_name) = LOWER(p.last_name || ', ' || p.first_name)
                AND (
                    rc.affiliation_state = p.state
                    OR rc.affiliation_state IS NULL
                    OR p.state IS NULL
                )
        ),
        -- Fuzzy matches (similarity >= 0.85) where no exact match exists
        fuzzy_matches AS (
            SELECT
                rc.researcher_id,
                p.provider_id,
                similarity(
                    LOWER(rc.canonical_full_name),
                    LOWER(p.last_name || ', ' || p.first_name)
                )::numeric                      AS confidence,
                'name+state_fuzzy'              AS matched_via
            FROM researcher_chunk rc
            JOIN hcs_silver.providers p
                ON similarity(
                    LOWER(rc.canonical_full_name),
                    LOWER(p.last_name || ', ' || p.first_name)
                ) >= 0.85
                AND (
                    rc.affiliation_state = p.state
                    OR rc.affiliation_state IS NULL
                    OR p.state IS NULL
                )
            WHERE NOT EXISTS (
                SELECT 1 FROM exact_matches em
                WHERE em.researcher_id = rc.researcher_id
                  AND em.provider_id = p.provider_id
            )
        ),
        all_matches AS (
            SELECT * FROM exact_matches
            UNION ALL
            SELECT * FROM fuzzy_matches
        ),
        inserted AS (
            INSERT INTO hcp_silver.researcher_provider_crosswalk (
                researcher_id,
                provider_id,
                confidence,
                matched_via
            )
            SELECT
                researcher_id,
                provider_id,
                confidence,
                matched_via
            FROM all_matches
            WHERE confidence >= 0.85
            ON CONFLICT (researcher_id, provider_id) DO UPDATE SET
                confidence  = GREATEST(EXCLUDED.confidence, hcp_silver.researcher_provider_crosswalk.confidence),
                matched_via = CASE
                    WHEN EXCLUDED.confidence > hcp_silver.researcher_provider_crosswalk.confidence
                    THEN EXCLUDED.matched_via
                    ELSE hcp_silver.researcher_provider_crosswalk.matched_via
                END
            RETURNING researcher_id
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        SELECT COALESCE(MAX(r.researcher_id), v_resume_pos) INTO v_new_pos
        FROM hcp_silver.researchers r
        WHERE r.researcher_id > v_resume_pos
        ORDER BY r.researcher_id
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

        EXIT WHEN v_new_pos = v_resume_pos;
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

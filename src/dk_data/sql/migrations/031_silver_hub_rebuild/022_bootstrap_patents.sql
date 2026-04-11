-- T078: Bootstrap ip_silver.patents from USPTO + EPO + USPTO CI sources
-- Expected: ~5M rows (Tier 2)
-- Also joins mol_bronze.orange_book to populate patent_identifiers with molecule linkages
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE ip_silver.bootstrap_patents()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'ip_silver.bootstrap_patents';
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
    VALUES (v_proc_name, pg_backend_pid()::text, NOW(), NOW() + INTERVAL '6 hours')
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
                ROW_NUMBER() OVER (ORDER BY source_priority, src_id) AS union_id,
                jurisdiction,
                patent_number,
                application_number,
                title,
                first_assignee,
                filing_date,
                grant_date,
                expiry_date,
                source_name
            FROM (
                -- USPTO patents
                SELECT 1 AS source_priority, id AS src_id,
                    'US'                AS jurisdiction,
                    patent_number,
                    application_number,
                    title,
                    first_assignee,
                    filing_date,
                    grant_date,
                    expiry_date,
                    'uspto_patents'     AS source_name
                FROM ip_bronze.uspto_patents

                UNION ALL

                -- EPO patents
                SELECT 2, id,
                    'EP',
                    patent_number,
                    application_number,
                    title,
                    first_assignee,
                    filing_date,
                    grant_date,
                    expiry_date,
                    'epo_patents'
                FROM ip_bronze.epo_patents

                UNION ALL

                -- USPTO Continuity (CI) — reuse patent_number from application chain
                SELECT 3, id,
                    'US',
                    child_patent_number AS patent_number,
                    child_application_number AS application_number,
                    NULL                AS title,
                    NULL                AS first_assignee,
                    NULL                AS filing_date,
                    NULL                AS grant_date,
                    NULL                AS expiry_date,
                    'uspto_ci'
                FROM ip_bronze.uspto_ci
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
            INSERT INTO ip_silver.patents (
                jurisdiction,
                patent_number,
                application_number,
                title,
                first_assignee,
                filing_date,
                grant_date,
                expiry_date
            )
            SELECT
                c.jurisdiction,
                c.patent_number,
                c.application_number,
                c.title,
                c.first_assignee,
                c.filing_date::date,
                c.grant_date::date,
                c.expiry_date::date
            FROM chunked c
            ON CONFLICT (jurisdiction, patent_number) WHERE patent_number IS NOT NULL DO NOTHING
            RETURNING patent_id, jurisdiction, patent_number, application_number
        ),
        id_insert AS (
            INSERT INTO ip_silver.patent_identifiers (source, identifier, patent_id, is_primary)
            SELECT
                c.source_name,
                c.patent_number,
                i.patent_id,
                true
            FROM chunked c
            JOIN inserted i ON i.jurisdiction = c.jurisdiction
                AND i.patent_number = c.patent_number
            WHERE c.patent_number IS NOT NULL
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        -- Orange Book join: link patents to molecules via inchi_key/application_number
        ob_link_insert AS (
            INSERT INTO ip_silver.patent_identifiers (source, identifier, patent_id, is_primary)
            SELECT
                'orange_book_molecule',
                m.inchi_key,
                i.patent_id,
                false
            FROM inserted i
            JOIN mol_bronze.orange_book ob ON ob.patent_number = i.patent_number
                AND i.jurisdiction = 'US'
            JOIN mol_silver.molecules m ON m.inchi_key = ob.inchi_key
            WHERE m.inchi_key IS NOT NULL
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        name_insert AS (
            INSERT INTO ip_silver.patent_names (normalized_name, patent_id, name_kind, source, display_name)
            SELECT
                LOWER(TRIM(c.title)),
                i.patent_id,
                'title',
                c.source_name,
                c.title
            FROM chunked c
            JOIN inserted i ON i.jurisdiction = c.jurisdiction
                AND i.patent_number = c.patent_number
            WHERE c.title IS NOT NULL
            ON CONFLICT (normalized_name, patent_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        SELECT COALESCE(MAX(union_id), v_resume_pos) INTO v_new_pos
        FROM (
            SELECT ROW_NUMBER() OVER (ORDER BY source_priority, src_id) AS union_id
            FROM (
                SELECT 1 AS source_priority, id AS src_id FROM ip_bronze.uspto_patents
                UNION ALL
                SELECT 2, id FROM ip_bronze.epo_patents
                UNION ALL
                SELECT 3, id FROM ip_bronze.uspto_ci
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

-- T070: Bootstrap hcs_silver.facilities from hcs_bronze.cms_nppes
-- Expected: ~6K rows (smallest Tier 0)
-- Chunk: ≤50K rows, ≤200 MB WAL per chunk, pg_sleep(0.05) between chunks

CREATE OR REPLACE PROCEDURE hcs_silver.bootstrap_facilities()
LANGUAGE plpgsql
AS $$
DECLARE
    v_proc_name  text := 'hcs_silver.bootstrap_facilities';
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

        -- Insert facilities hub rows
        WITH inserted AS (
            INSERT INTO hcs_silver.facilities (
                ccn,
                npi_type2,
                facility_name,
                city,
                state,
                zip,
                ownership_type
            )
            SELECT DISTINCT ON (src.ccn)
                src.ccn,
                src.npi                    AS npi_type2,
                src.provider_organization_name_legal_business_name AS facility_name,
                src.provider_business_practice_location_address_city_name  AS city,
                src.provider_business_practice_location_address_state_name AS state,
                src.provider_business_practice_location_address_postal_code AS zip,
                src.healthcare_provider_taxonomy_code_1 AS ownership_type
            FROM hcs_bronze.cms_nppes src
            WHERE src.entity_type_code = '2'          -- Type 2 = organizations/facilities
              AND src.facility_type IS NOT NULL
              AND src.ccn IS NOT NULL
              AND src.id > v_resume_pos
            ORDER BY src.ccn, src.id
            LIMIT v_chunk_size
            ON CONFLICT (ccn) DO NOTHING
            RETURNING facility_id
        ),
        id_insert AS (
            -- Populate facility_identifiers for NPI Type 2
            INSERT INTO hcs_silver.facility_identifiers (source, identifier, facility_id, is_primary)
            SELECT
                'npi_type2',
                src.npi,
                f.facility_id,
                true
            FROM hcs_bronze.cms_nppes src
            JOIN hcs_silver.facilities f ON f.ccn = src.ccn
            WHERE src.entity_type_code = '2'
              AND src.facility_type IS NOT NULL
              AND src.ccn IS NOT NULL
              AND src.id > v_resume_pos
            ORDER BY src.id
            LIMIT v_chunk_size
            ON CONFLICT (source, identifier) DO NOTHING
        ),
        name_insert AS (
            -- Populate facility_names
            INSERT INTO hcs_silver.facility_names (normalized_name, facility_id, name_kind, source, display_name)
            SELECT
                LOWER(TRIM(src.provider_organization_name_legal_business_name)),
                f.facility_id,
                'canonical',
                'cms_nppes',
                src.provider_organization_name_legal_business_name
            FROM hcs_bronze.cms_nppes src
            JOIN hcs_silver.facilities f ON f.ccn = src.ccn
            WHERE src.entity_type_code = '2'
              AND src.facility_type IS NOT NULL
              AND src.ccn IS NOT NULL
              AND src.id > v_resume_pos
            ORDER BY src.id
            LIMIT v_chunk_size
            ON CONFLICT (normalized_name, facility_id, source) DO NOTHING
        )
        SELECT COUNT(*) INTO v_rows FROM inserted;

        v_end_lsn := pg_current_wal_lsn();

        -- Get new resume position
        SELECT COALESCE(MAX(src.id), v_resume_pos) INTO v_new_pos
        FROM hcs_bronze.cms_nppes src
        WHERE src.entity_type_code = '2'
          AND src.facility_type IS NOT NULL
          AND src.ccn IS NOT NULL
          AND src.id > v_resume_pos
        ORDER BY src.id
        LIMIT v_chunk_size;

        -- d. Record transform run
        INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
        VALUES (
            v_proc_name,
            v_new_pos::text,
            v_started_at,
            clock_timestamp(),
            v_rows,
            pg_wal_lsn_diff(v_end_lsn, v_start_lsn)
        );

        -- e. Update resume position
        UPDATE meta.refresh_state
        SET last_chunk_position = v_new_pos::text,
            last_commit_at      = NOW()
        WHERE procedure_name = v_proc_name;

        -- f. Commit chunk
        COMMIT;

        EXIT WHEN v_rows = 0 OR v_new_pos = v_resume_pos;
        v_resume_pos := v_new_pos;

        -- g. Brief pause to reduce multi-tenant contention
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

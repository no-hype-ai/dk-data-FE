-- Migration 031/030: Tray procedure for mol_bronze.chembl_activities
-- Feature: 001-silver-medallion-rebuild / T150
--
-- Creates mol_bronze.refresh_chembl_activities_via_tray() which rebuilds the
-- chembl_activities bronze table atomically via an unlogged tray table.
--
-- Pattern:
--   1. CREATE UNLOGGED tray table (LIKE target INCLUDING ALL)
--   2. Chunked COPY/INSERT into tray with meta.transform_runs accounting
--   3. SET TABLE tray LOGGED (WAL-flush before swap)
--   4. DROP non-essential indexes on target (preserves PKs/unique constraints)
--   5. Atomic swap via ALTER TABLE RENAME (target→old, tray→target)
--   6. DROP old table, recreate non-essential indexes
--
-- FR-021: Max chunk size 50K rows / 200 MB WAL. pg_sleep(0.05) between chunks.

CREATE OR REPLACE PROCEDURE mol_bronze.refresh_chembl_activities_via_tray()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size    CONSTANT INT     := 50000;
    v_sleep_ms      CONSTANT NUMERIC := 0.05;
    v_tray_name     CONSTANT TEXT    := 'chembl_activities_tray';
    v_target_name   CONSTANT TEXT    := 'chembl_activities';
    v_old_name      CONSTANT TEXT    := 'chembl_activities_old';
    v_schema        CONSTANT TEXT    := 'mol_bronze';
    v_offset        INT              := 0;
    v_rows_inserted INT              := 0;
    v_chunk_rows    INT;
    v_wal_start     pg_lsn;
    v_wal_end       pg_lsn;
    v_wal_bytes     BIGINT;
    v_chunk_pos     INT              := 0;
    v_run_id        BIGINT;
BEGIN
    -- ----------------------------------------------------------------
    -- Step 1: Create unlogged tray table
    -- ----------------------------------------------------------------
    EXECUTE format(
        'DROP TABLE IF EXISTS %I.%I CASCADE',
        v_schema, v_tray_name
    );
    EXECUTE format(
        'CREATE UNLOGGED TABLE %I.%I (LIKE %I.%I INCLUDING ALL)',
        v_schema, v_tray_name, v_schema, v_target_name
    );

    -- ----------------------------------------------------------------
    -- Step 2: Chunked INSERT into tray with WAL accounting
    -- ----------------------------------------------------------------
    LOOP
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

        EXECUTE format(
            'INSERT INTO %I.%I
             SELECT * FROM %I.%I
             ORDER BY activity_id
             LIMIT %L OFFSET %L',
            v_schema, v_tray_name,
            v_schema, v_target_name,
            v_chunk_size, v_offset
        );

        GET DIAGNOSTICS v_chunk_rows = ROW_COUNT;
        EXIT WHEN v_chunk_rows = 0;

        v_wal_end   := pg_current_wal_lsn();
        v_wal_bytes := pg_wal_lsn_diff(v_wal_end, v_wal_start);

        -- Record chunk in meta.transform_runs
        INSERT INTO meta.transform_runs (
            procedure_name, chunk_position, rows_processed, wal_bytes, started_at
        ) VALUES (
            'mol_bronze.refresh_chembl_activities_via_tray',
            v_chunk_pos, v_chunk_rows, v_wal_bytes, NOW()
        ) ON CONFLICT DO NOTHING;

        v_rows_inserted := v_rows_inserted + v_chunk_rows;
        v_offset        := v_offset + v_chunk_size;

        PERFORM pg_sleep(v_sleep_ms);
        COMMIT;

        EXIT WHEN v_chunk_rows < v_chunk_size;
    END LOOP;

    -- ----------------------------------------------------------------
    -- Step 3: Make tray LOGGED before swap
    -- ----------------------------------------------------------------
    EXECUTE format('ALTER TABLE %I.%I SET LOGGED', v_schema, v_tray_name);
    COMMIT;

    -- ----------------------------------------------------------------
    -- Step 4: Drop non-essential indexes on target
    -- (Unique/PK constraints are preserved; lookup/perf indexes dropped)
    -- NOTE: Once T161 index audit completes, list non-essential indexes here.
    -- ----------------------------------------------------------------
    -- Example: DROP INDEX CONCURRENTLY IF EXISTS mol_bronze.idx_chembl_activities_molregno;

    -- ----------------------------------------------------------------
    -- Step 5: Atomic swap
    -- ----------------------------------------------------------------
    EXECUTE format('ALTER TABLE %I.%I RENAME TO %I', v_schema, v_target_name, v_old_name);
    EXECUTE format('ALTER TABLE %I.%I RENAME TO %I', v_schema, v_tray_name, v_target_name);
    COMMIT;

    -- ----------------------------------------------------------------
    -- Step 6: Drop old table and recreate non-essential indexes
    -- ----------------------------------------------------------------
    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', v_schema, v_old_name);
    -- Example: CREATE INDEX CONCURRENTLY idx_chembl_activities_molregno ON mol_bronze.chembl_activities (molregno);
    COMMIT;

    RAISE NOTICE 'refresh_chembl_activities_via_tray complete: % rows inserted', v_rows_inserted;
END;
$$;

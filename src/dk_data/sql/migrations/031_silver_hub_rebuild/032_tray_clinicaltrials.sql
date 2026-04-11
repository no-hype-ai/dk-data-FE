-- Migration 031/032_tray_clinicaltrials.sql: Tray procedure for mol_bronze.clinicaltrials
-- Feature: 001-silver-medallion-rebuild / T151-T154
--
-- Atomically rebuilds mol_bronze.clinicaltrials via unlogged tray table.
-- Max chunk size 50K rows / 200 MB WAL. pg_sleep(0.05) between chunks.

CREATE OR REPLACE PROCEDURE mol_bronze.refresh_clinicaltrials_via_tray()
LANGUAGE plpgsql
AS $$
DECLARE
    v_chunk_size    CONSTANT INT     := 50000;
    v_sleep_ms      CONSTANT NUMERIC := 0.05;
    v_tray_name     CONSTANT TEXT    := 'clinicaltrials_tray';
    v_target_name   CONSTANT TEXT    := 'clinicaltrials';
    v_old_name      CONSTANT TEXT    := 'clinicaltrials_old';
    v_schema        CONSTANT TEXT    := 'mol_bronze';
    v_offset        INT              := 0;
    v_rows_inserted INT              := 0;
    v_chunk_rows    INT;
    v_wal_start     pg_lsn;
    v_wal_end       pg_lsn;
    v_wal_bytes     BIGINT;
    v_chunk_pos     INT              := 0;
BEGIN
    -- Step 1: Create unlogged tray table
    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', v_schema, v_tray_name);
    EXECUTE format(
        'CREATE UNLOGGED TABLE %I.%I (LIKE %I.%I INCLUDING ALL)',
        v_schema, v_tray_name, v_schema, v_target_name
    );

    -- Step 2: Chunked INSERT into tray with WAL accounting
    LOOP
        v_wal_start := pg_current_wal_lsn();
        v_chunk_pos := v_chunk_pos + 1;

        EXECUTE format(
            'INSERT INTO %I.%I SELECT * FROM %I.%I ORDER BY nct_id LIMIT %L OFFSET %L',
            v_schema, v_tray_name, v_schema, v_target_name, v_chunk_size, v_offset
        );
        GET DIAGNOSTICS v_chunk_rows = ROW_COUNT;
        EXIT WHEN v_chunk_rows = 0;

        v_wal_end   := pg_current_wal_lsn();
        v_wal_bytes := pg_wal_lsn_diff(v_wal_end, v_wal_start);

        INSERT INTO meta.transform_runs (
            procedure_name, chunk_position, rows_processed, wal_bytes, started_at
        ) VALUES (
            'mol_bronze.refresh_clinicaltrials_via_tray', v_chunk_pos, v_chunk_rows, v_wal_bytes, NOW()
        ) ON CONFLICT DO NOTHING;

        v_rows_inserted := v_rows_inserted + v_chunk_rows;
        v_offset        := v_offset + v_chunk_size;
        PERFORM pg_sleep(v_sleep_ms);
        COMMIT;
        EXIT WHEN v_chunk_rows < v_chunk_size;
    END LOOP;

    -- Step 3: Make tray LOGGED before swap
    EXECUTE format('ALTER TABLE %I.%I SET LOGGED', v_schema, v_tray_name);
    COMMIT;

    -- Step 4: Drop non-essential indexes on target
    -- NOTE: List non-essential indexes here once T161 audit completes.

    -- Step 5: Atomic swap
    EXECUTE format('ALTER TABLE %I.%I RENAME TO %I', v_schema, v_target_name, v_old_name);
    EXECUTE format('ALTER TABLE %I.%I RENAME TO %I', v_schema, v_tray_name, v_target_name);
    COMMIT;

    -- Step 6: Drop old table and recreate non-essential indexes
    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', v_schema, v_old_name);
    COMMIT;

    RAISE NOTICE 'refresh_clinicaltrials_via_tray complete: % rows inserted', v_rows_inserted;
END;
$$;

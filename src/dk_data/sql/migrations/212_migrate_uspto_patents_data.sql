-- Migration 051: Migrate mol_bronze.uspto_patents → ip_bronze.uspto_patents
-- Part of: 001-silver-medallion-rebuild (FR-006d, FR-021)
-- Chunked PL/pgSQL: ≤50K rows/chunk, pg_sleep(0.05) between chunks, WAL tracking
-- NOTE: Run AFTER 050_create_ip_schemas.sql and after SQLMesh has created ip_bronze.uspto_patents table.

CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_bronze_uspto_patents()
LANGUAGE plpgsql AS $$
DECLARE
  v_chunk_size INT := 50000;
  v_offset BIGINT := 0;
  v_rows_moved BIGINT;
  v_start_lsn pg_lsn;
  v_end_lsn pg_lsn;
  v_resume_pos TEXT;
BEGIN
  -- Guard: skip if target schema has no tables (CI/fresh deploy — SQLMesh hasn't run yet)
  IF NOT EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema = 'ip_bronze'
  ) THEN
      RAISE NOTICE 'ip_bronze has no tables — skipping migration';
      RETURN;
  END IF;

  -- Resume from last checkpoint
  SELECT last_chunk_position INTO v_resume_pos
  FROM meta.refresh_state WHERE procedure_name = 'migrate_uspto_patents';
  IF FOUND AND v_resume_pos IS NOT NULL THEN
    v_offset := v_resume_pos::BIGINT;
  END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_uspto_patents', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET
    status = 'in_progress',
    last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();

    INSERT INTO ip_bronze.uspto_patents
    SELECT * FROM mol_bronze.uspto_patents
    ORDER BY ctid
    LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (patent_number) DO NOTHING;

    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;

    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;

    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_uspto_patents', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));

    UPDATE meta.refresh_state SET
      last_chunk_position = v_offset::TEXT,
      last_commit_at = NOW()
    WHERE procedure_name = 'migrate_uspto_patents';

    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  -- Verify row count
  ASSERT (SELECT COUNT(*) FROM ip_bronze.uspto_patents) >= (SELECT COUNT(*) FROM mol_bronze.uspto_patents) * 0.999,
    'Row count mismatch after migration: ip_bronze has fewer rows than mol_bronze';

  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_uspto_patents';
  COMMIT;

  RAISE NOTICE 'Migration complete: migrate_uspto_patents — % total rows', v_offset;
END;
$$;

-- Execute the migration

-- NOTE: DROP TABLE mol_bronze.uspto_patents must be run AFTER verification in a separate transaction.
-- Verify with: SELECT count(*) FROM ip_bronze.uspto_patents;
--              SELECT count(*) FROM mol_bronze.uspto_patents;

-- NOTE: These procedures are not called by this migration.
-- Run them manually after SQLMesh has created the target tables:
--   CALL migrate_mol_to_ip_bronze_uspto_patents();

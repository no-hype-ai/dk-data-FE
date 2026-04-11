-- Migration 052: Migrate remaining IP bronze tables mol_bronze → ip_bronze
-- Part of: 001-silver-medallion-rebuild (FR-006d, FR-021)
-- Tables: uspto_ci, uspto_trademarks, epo_patents, euipo_trademarks, euipo_designs, trademark_status_history
-- Chunked PL/pgSQL: ≤50K rows/chunk, pg_sleep(0.05) between chunks, WAL tracking
-- NOTE: Run AFTER 050_create_ip_schemas.sql and after SQLMesh has created ip_bronze.* tables.

-- ============================================================
-- uspto_ci
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_bronze_uspto_ci()
LANGUAGE plpgsql AS $$
DECLARE
  v_chunk_size INT := 50000;
  v_offset BIGINT := 0;
  v_rows_moved BIGINT;
  v_start_lsn pg_lsn;
  v_end_lsn pg_lsn;
  v_resume_pos TEXT;
BEGIN
  SELECT last_chunk_position INTO v_resume_pos
  FROM meta.refresh_state WHERE procedure_name = 'migrate_uspto_ci';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_uspto_ci', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_bronze.uspto_ci
    SELECT * FROM mol_bronze.uspto_ci ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (patent_number) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_uspto_ci', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_uspto_ci';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_bronze.uspto_ci) >= (SELECT COUNT(*) FROM mol_bronze.uspto_ci) * 0.999,
    'Row count mismatch: ip_bronze.uspto_ci';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_uspto_ci';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_uspto_ci — % total rows', v_offset;
END;
$$;

-- ============================================================
-- uspto_trademarks
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_bronze_uspto_trademarks()
LANGUAGE plpgsql AS $$
DECLARE
  v_chunk_size INT := 50000;
  v_offset BIGINT := 0;
  v_rows_moved BIGINT;
  v_start_lsn pg_lsn;
  v_end_lsn pg_lsn;
  v_resume_pos TEXT;
BEGIN
  SELECT last_chunk_position INTO v_resume_pos
  FROM meta.refresh_state WHERE procedure_name = 'migrate_uspto_trademarks';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_uspto_trademarks', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_bronze.uspto_trademarks
    SELECT * FROM mol_bronze.uspto_trademarks ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (serial_number) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_uspto_trademarks', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_uspto_trademarks';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_bronze.uspto_trademarks) >= (SELECT COUNT(*) FROM mol_bronze.uspto_trademarks) * 0.999,
    'Row count mismatch: ip_bronze.uspto_trademarks';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_uspto_trademarks';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_uspto_trademarks — % total rows', v_offset;
END;
$$;

-- ============================================================
-- epo_patents
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_bronze_epo_patents()
LANGUAGE plpgsql AS $$
DECLARE
  v_chunk_size INT := 50000;
  v_offset BIGINT := 0;
  v_rows_moved BIGINT;
  v_start_lsn pg_lsn;
  v_end_lsn pg_lsn;
  v_resume_pos TEXT;
BEGIN
  SELECT last_chunk_position INTO v_resume_pos
  FROM meta.refresh_state WHERE procedure_name = 'migrate_epo_patents';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_epo_patents', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_bronze.epo_patents
    SELECT * FROM mol_bronze.epo_patents ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (patent_number) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_epo_patents', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_epo_patents';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_bronze.epo_patents) >= (SELECT COUNT(*) FROM mol_bronze.epo_patents) * 0.999,
    'Row count mismatch: ip_bronze.epo_patents';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_epo_patents';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_epo_patents — % total rows', v_offset;
END;
$$;

-- ============================================================
-- euipo_trademarks
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_bronze_euipo_trademarks()
LANGUAGE plpgsql AS $$
DECLARE
  v_chunk_size INT := 50000;
  v_offset BIGINT := 0;
  v_rows_moved BIGINT;
  v_start_lsn pg_lsn;
  v_end_lsn pg_lsn;
  v_resume_pos TEXT;
BEGIN
  SELECT last_chunk_position INTO v_resume_pos
  FROM meta.refresh_state WHERE procedure_name = 'migrate_euipo_trademarks';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_euipo_trademarks', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_bronze.euipo_trademarks
    SELECT * FROM mol_bronze.euipo_trademarks ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (application_number) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_euipo_trademarks', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_euipo_trademarks';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_bronze.euipo_trademarks) >= (SELECT COUNT(*) FROM mol_bronze.euipo_trademarks) * 0.999,
    'Row count mismatch: ip_bronze.euipo_trademarks';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_euipo_trademarks';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_euipo_trademarks — % total rows', v_offset;
END;
$$;

-- ============================================================
-- euipo_designs
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_bronze_euipo_designs()
LANGUAGE plpgsql AS $$
DECLARE
  v_chunk_size INT := 50000;
  v_offset BIGINT := 0;
  v_rows_moved BIGINT;
  v_start_lsn pg_lsn;
  v_end_lsn pg_lsn;
  v_resume_pos TEXT;
BEGIN
  SELECT last_chunk_position INTO v_resume_pos
  FROM meta.refresh_state WHERE procedure_name = 'migrate_euipo_designs';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_euipo_designs', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_bronze.euipo_designs
    SELECT * FROM mol_bronze.euipo_designs ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (application_number) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_euipo_designs', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_euipo_designs';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_bronze.euipo_designs) >= (SELECT COUNT(*) FROM mol_bronze.euipo_designs) * 0.999,
    'Row count mismatch: ip_bronze.euipo_designs';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_euipo_designs';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_euipo_designs — % total rows', v_offset;
END;
$$;

-- ============================================================
-- trademark_status_history
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_bronze_trademark_status_history()
LANGUAGE plpgsql AS $$
DECLARE
  v_chunk_size INT := 50000;
  v_offset BIGINT := 0;
  v_rows_moved BIGINT;
  v_start_lsn pg_lsn;
  v_end_lsn pg_lsn;
  v_resume_pos TEXT;
BEGIN
  SELECT last_chunk_position INTO v_resume_pos
  FROM meta.refresh_state WHERE procedure_name = 'migrate_trademark_status_history';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_trademark_status_history', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_bronze.trademark_status_history
    SELECT * FROM mol_bronze.trademark_status_history ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (trademark_identifier, source, changed_at) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_trademark_status_history', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_trademark_status_history';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_bronze.trademark_status_history) >= (SELECT COUNT(*) FROM mol_bronze.trademark_status_history) * 0.999,
    'Row count mismatch: ip_bronze.trademark_status_history';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_trademark_status_history';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_trademark_status_history — % total rows', v_offset;
END;
$$;

-- Execute all migrations in sequence
CALL migrate_mol_to_ip_bronze_uspto_ci();
CALL migrate_mol_to_ip_bronze_uspto_trademarks();
CALL migrate_mol_to_ip_bronze_epo_patents();
CALL migrate_mol_to_ip_bronze_euipo_trademarks();
CALL migrate_mol_to_ip_bronze_euipo_designs();
CALL migrate_mol_to_ip_bronze_trademark_status_history();

-- NOTE: DROP TABLE mol_bronze.<table> must be run AFTER verification in separate transactions.
-- Verification queries:
--   SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'ip_bronze';
--   SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'mol_bronze' AND tablename IN ('uspto_ci','uspto_trademarks','epo_patents','euipo_trademarks','euipo_designs','trademark_status_history');

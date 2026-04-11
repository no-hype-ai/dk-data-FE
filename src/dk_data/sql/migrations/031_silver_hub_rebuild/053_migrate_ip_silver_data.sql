-- Migration 053: Migrate IP silver tables mol_silver → ip_silver
-- Part of: 001-silver-medallion-rebuild (FR-006e, FR-021)
-- Tables: patents, trademarks, patent_exclusivities, trademark_status_changes, euipo_designs → designs (renamed)
-- Chunked PL/pgSQL: ≤50K rows/chunk, pg_sleep(0.05) between chunks, WAL tracking
-- NOTE: Run AFTER 050_create_ip_schemas.sql and after SQLMesh has created ip_silver.* tables.

-- ============================================================
-- patents (mol_silver.patents → ip_silver.patents)
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_silver_patents()
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
  FROM meta.refresh_state WHERE procedure_name = 'migrate_ip_silver_patents';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_ip_silver_patents', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_silver.patents
    SELECT * FROM mol_silver.patents ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (patent_number) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_ip_silver_patents', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_ip_silver_patents';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_silver.patents) >= (SELECT COUNT(*) FROM mol_silver.patents) * 0.999,
    'Row count mismatch: ip_silver.patents';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_ip_silver_patents';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_ip_silver_patents — % total rows', v_offset;
END;
$$;

-- ============================================================
-- trademarks (mol_silver.trademarks → ip_silver.trademarks)
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_silver_trademarks()
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
  FROM meta.refresh_state WHERE procedure_name = 'migrate_ip_silver_trademarks';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_ip_silver_trademarks', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_silver.trademarks
    SELECT * FROM mol_silver.trademarks ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (trademark_identifier, source) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_ip_silver_trademarks', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_ip_silver_trademarks';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_silver.trademarks) >= (SELECT COUNT(*) FROM mol_silver.trademarks) * 0.999,
    'Row count mismatch: ip_silver.trademarks';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_ip_silver_trademarks';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_ip_silver_trademarks — % total rows', v_offset;
END;
$$;

-- ============================================================
-- patent_exclusivities (mol_silver.patent_exclusivities → ip_silver.patent_exclusivities)
-- FULL model — no unique key conflict, use INSERT SELECT directly with chunking
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_silver_patent_exclusivities()
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
  FROM meta.refresh_state WHERE procedure_name = 'migrate_ip_silver_patent_exclusivities';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_ip_silver_patent_exclusivities', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_silver.patent_exclusivities
    SELECT * FROM mol_silver.patent_exclusivities ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_ip_silver_patent_exclusivities', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_ip_silver_patent_exclusivities';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_silver.patent_exclusivities) >= (SELECT COUNT(*) FROM mol_silver.patent_exclusivities) * 0.999,
    'Row count mismatch: ip_silver.patent_exclusivities';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_ip_silver_patent_exclusivities';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_ip_silver_patent_exclusivities — % total rows', v_offset;
END;
$$;

-- ============================================================
-- trademark_status_changes (mol_silver.trademark_status_changes → ip_silver.trademark_status_changes)
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_silver_trademark_status_changes()
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
  FROM meta.refresh_state WHERE procedure_name = 'migrate_ip_silver_trademark_status_changes';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_ip_silver_trademark_status_changes', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    INSERT INTO ip_silver.trademark_status_changes
    SELECT * FROM mol_silver.trademark_status_changes ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset
    ON CONFLICT (trademark_identifier, source, changed_at) DO NOTHING;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_ip_silver_trademark_status_changes', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_ip_silver_trademark_status_changes';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_silver.trademark_status_changes) >= (SELECT COUNT(*) FROM mol_silver.trademark_status_changes) * 0.999,
    'Row count mismatch: ip_silver.trademark_status_changes';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_ip_silver_trademark_status_changes';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_ip_silver_trademark_status_changes — % total rows', v_offset;
END;
$$;

-- ============================================================
-- designs (mol_silver.euipo_designs → ip_silver.designs — renamed)
-- FULL model — no unique key, chunked INSERT
-- ============================================================
CREATE OR REPLACE PROCEDURE migrate_mol_to_ip_silver_designs()
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
  FROM meta.refresh_state WHERE procedure_name = 'migrate_ip_silver_designs';
  IF FOUND AND v_resume_pos IS NOT NULL THEN v_offset := v_resume_pos::BIGINT; END IF;

  INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
  VALUES ('migrate_ip_silver_designs', v_offset::TEXT, 'in_progress')
  ON CONFLICT (procedure_name) DO UPDATE SET status = 'in_progress', last_chunk_position = EXCLUDED.last_chunk_position;
  COMMIT;

  LOOP
    v_start_lsn := pg_current_wal_lsn();
    -- Source is mol_silver.euipo_designs; destination is ip_silver.designs (renamed)
    INSERT INTO ip_silver.designs
    SELECT * FROM mol_silver.euipo_designs ORDER BY ctid LIMIT v_chunk_size OFFSET v_offset;
    GET DIAGNOSTICS v_rows_moved = ROW_COUNT;
    EXIT WHEN v_rows_moved = 0;
    v_end_lsn := pg_current_wal_lsn();
    v_offset := v_offset + v_rows_moved;
    INSERT INTO meta.transform_runs (procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes)
    VALUES ('migrate_ip_silver_designs', v_offset::TEXT, NOW(), NOW(), v_rows_moved, pg_wal_lsn_diff(v_end_lsn, v_start_lsn));
    UPDATE meta.refresh_state SET last_chunk_position = v_offset::TEXT, last_commit_at = NOW() WHERE procedure_name = 'migrate_ip_silver_designs';
    COMMIT;
    PERFORM pg_sleep(0.05);
  END LOOP;

  ASSERT (SELECT COUNT(*) FROM ip_silver.designs) >= (SELECT COUNT(*) FROM mol_silver.euipo_designs) * 0.999,
    'Row count mismatch: ip_silver.designs (from mol_silver.euipo_designs)';
  UPDATE meta.refresh_state SET status = 'completed' WHERE procedure_name = 'migrate_ip_silver_designs';
  COMMIT;
  RAISE NOTICE 'Migration complete: migrate_ip_silver_designs — % total rows', v_offset;
END;
$$;

-- Execute all silver migrations in sequence
CALL migrate_mol_to_ip_silver_patents();
CALL migrate_mol_to_ip_silver_trademarks();
CALL migrate_mol_to_ip_silver_patent_exclusivities();
CALL migrate_mol_to_ip_silver_trademark_status_changes();
CALL migrate_mol_to_ip_silver_designs();

-- NOTE: DROP TABLE mol_silver.<table> must be run AFTER verification in separate transactions.
-- Recommended verification:
--   SELECT 'patents' AS tbl, count(*) FROM ip_silver.patents
--   UNION ALL SELECT 'trademarks', count(*) FROM ip_silver.trademarks
--   UNION ALL SELECT 'patent_exclusivities', count(*) FROM ip_silver.patent_exclusivities
--   UNION ALL SELECT 'trademark_status_changes', count(*) FROM ip_silver.trademark_status_changes
--   UNION ALL SELECT 'designs', count(*) FROM ip_silver.designs;

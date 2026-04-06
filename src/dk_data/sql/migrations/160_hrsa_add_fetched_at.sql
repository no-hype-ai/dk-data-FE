-- Migration 158: Add _fetched_at column to hcs_raw.hrsa_shortage_areas
--
-- Root cause: init_database.sql creates raw.hrsa_shortage_areas with _loaded_at
-- but not _fetched_at. Migration 099 moves it to hcs_raw; migration 105's
-- CREATE TABLE IF NOT EXISTS is then a no-op and _fetched_at is never added.
-- The hcs_bronze.hrsa SQLMesh model references _fetched_at as its time_column.

ALTER TABLE hcs_raw.hrsa_shortage_areas
    ADD COLUMN IF NOT EXISTS _fetched_at TIMESTAMPTZ DEFAULT NOW();

-- Backfill _fetched_at from _loaded_at if that column exists (init_database.sql path).
-- In production (migration 105 path), _loaded_at doesn't exist so we skip.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'hcs_raw'
      AND table_name = 'hrsa_shortage_areas'
      AND column_name = '_loaded_at'
  ) THEN
    UPDATE hcs_raw.hrsa_shortage_areas
    SET _fetched_at = _loaded_at::TIMESTAMPTZ
    WHERE _fetched_at IS NULL AND _loaded_at IS NOT NULL;
  END IF;
END $$;

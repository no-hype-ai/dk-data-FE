-- Migration 031/038_partition_clinicaltrials.sql: Partition mol_bronze.clinicaltrials by month on ingested_at
-- Feature: 001-silver-medallion-rebuild / T163-T167
--
-- Strategy: atomic ATTACH after backfill through tray (non-blocking with right timing).
-- This migration creates the partitioned parent table and attaches the first partition.
-- Existing data is moved via the tray procedure (030-034) before ATTACH.
--
-- NOTE: Run AFTER the corresponding tray procedure has loaded data into a clean table.
-- The swap is done via the tray rename, so ATTACH PARTITION is already on new data.

BEGIN;

-- Step 1: Rename target to preserve data during partition setup
ALTER TABLE mol_bronze.clinicaltrials RENAME TO clinicaltrials_nonpart;

-- Step 2: Create partitioned parent table
CREATE TABLE mol_bronze.clinicaltrials (
    LIKE mol_bronze.clinicaltrials_nonpart INCLUDING DEFAULTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (ingested_at);

-- Step 3: Create initial partitions (monthly, add more as needed)
CREATE TABLE mol_bronze.clinicaltrials_y2024m01
    PARTITION OF mol_bronze.clinicaltrials
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE mol_bronze.clinicaltrials_y2024m06
    PARTITION OF mol_bronze.clinicaltrials
    FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');

CREATE TABLE mol_bronze.clinicaltrials_y2025m01
    PARTITION OF mol_bronze.clinicaltrials
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE mol_bronze.clinicaltrials_y2025m06
    PARTITION OF mol_bronze.clinicaltrials
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE mol_bronze.clinicaltrials_y2026m01
    PARTITION OF mol_bronze.clinicaltrials
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- Default partition catches everything outside the above ranges
CREATE TABLE mol_bronze.clinicaltrials_default
    PARTITION OF mol_bronze.clinicaltrials DEFAULT;

-- Step 4: Copy data from non-partitioned table to partitioned parent
-- Chunked to stay under max_wal_size = 4 GB (reviewer flag: PR #275)
DO $$
DECLARE
    v_max_id BIGINT;
    v_low    BIGINT := 0;
    v_chunk  CONSTANT BIGINT := 50000;
    v_rows   INT;
BEGIN
    SELECT COALESCE(MAX(id), 0) INTO v_max_id FROM mol_bronze.clinicaltrials_nonpart;
    WHILE v_low < v_max_id LOOP
        INSERT INTO mol_bronze.clinicaltrials
        SELECT * FROM mol_bronze.clinicaltrials_nonpart
        WHERE id > v_low AND id <= v_low + v_chunk;
        GET DIAGNOSTICS v_rows = ROW_COUNT;
        v_low := v_low + v_chunk;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;
END $$;

-- Step 5: Drop old non-partitioned table
DROP TABLE mol_bronze.clinicaltrials_nonpart;

COMMIT;

-- NOTE: After partitioning, recreate BRIN indexes on each partition:
-- CREATE INDEX ON mol_bronze.clinicaltrials_y2026m01 USING BRIN (ingested_at);
-- etc. (handled by 035_brin_indexes.sql on the parent)

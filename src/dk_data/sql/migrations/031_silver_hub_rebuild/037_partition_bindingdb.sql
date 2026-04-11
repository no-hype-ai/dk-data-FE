-- Migration 031/037_partition_bindingdb.sql: Partition mol_bronze.bindingdb by month on ingested_at
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
ALTER TABLE mol_bronze.bindingdb RENAME TO bindingdb_nonpart;

-- Step 2: Create partitioned parent table
CREATE TABLE mol_bronze.bindingdb (
    LIKE mol_bronze.bindingdb_nonpart INCLUDING DEFAULTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (ingested_at);

-- Step 3: Create initial partitions (monthly, add more as needed)
CREATE TABLE mol_bronze.bindingdb_y2024m01
    PARTITION OF mol_bronze.bindingdb
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE mol_bronze.bindingdb_y2024m06
    PARTITION OF mol_bronze.bindingdb
    FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');

CREATE TABLE mol_bronze.bindingdb_y2025m01
    PARTITION OF mol_bronze.bindingdb
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE mol_bronze.bindingdb_y2025m06
    PARTITION OF mol_bronze.bindingdb
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE mol_bronze.bindingdb_y2026m01
    PARTITION OF mol_bronze.bindingdb
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- Default partition catches everything outside the above ranges
CREATE TABLE mol_bronze.bindingdb_default
    PARTITION OF mol_bronze.bindingdb DEFAULT;

-- Step 4: Copy data from non-partitioned table to partitioned parent
-- (Do this in chunks via the tray procedure for large tables)
INSERT INTO mol_bronze.bindingdb
SELECT * FROM mol_bronze.bindingdb_nonpart;

-- Step 5: Drop old non-partitioned table
DROP TABLE mol_bronze.bindingdb_nonpart;

COMMIT;

-- NOTE: After partitioning, recreate BRIN indexes on each partition:
-- CREATE INDEX ON mol_bronze.bindingdb_y2026m01 USING BRIN (ingested_at);
-- etc. (handled by 035_brin_indexes.sql on the parent)

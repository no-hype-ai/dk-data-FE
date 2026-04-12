-- Migration 031/036_partition_chembl_activities.sql: Partition mol_bronze.chembl_activities by month on ingested_at
-- Feature: 001-silver-medallion-rebuild / T163-T167
--
-- Strategy: rename existing table → create partitioned parent → copy data → drop old.
-- The copy uses a chunked procedure (CALL) so each batch commits independently,
-- keeping WAL below the CNPG cluster's 4 GB max_wal_size ceiling.
--
-- If the table is empty (fresh deploy), the copy is a no-op and completes instantly.

-- Step 1: DDL — rename, create partitioned parent, create partitions
BEGIN;

ALTER TABLE mol_bronze.chembl_activities RENAME TO chembl_activities_nonpart;

CREATE TABLE mol_bronze.chembl_activities (
    LIKE mol_bronze.chembl_activities_nonpart INCLUDING DEFAULTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (ingested_at);

CREATE TABLE mol_bronze.chembl_activities_y2024m01
    PARTITION OF mol_bronze.chembl_activities
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE mol_bronze.chembl_activities_y2024m06
    PARTITION OF mol_bronze.chembl_activities
    FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');

CREATE TABLE mol_bronze.chembl_activities_y2025m01
    PARTITION OF mol_bronze.chembl_activities
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE mol_bronze.chembl_activities_y2025m06
    PARTITION OF mol_bronze.chembl_activities
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

CREATE TABLE mol_bronze.chembl_activities_y2026m01
    PARTITION OF mol_bronze.chembl_activities
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE mol_bronze.chembl_activities_default
    PARTITION OF mol_bronze.chembl_activities DEFAULT;

-- Step 2: Create a temporary procedure for chunked copy with per-batch COMMIT.
-- PROCEDURE (not DO block) is required for transaction control statements.
CREATE OR REPLACE PROCEDURE _tmp_partition_copy_chembl_activities()
LANGUAGE plpgsql AS $$
DECLARE
    v_max_id BIGINT;
    v_low    BIGINT := 0;
    v_chunk  CONSTANT BIGINT := 50000;
BEGIN
    SELECT COALESCE(MAX(id), 0) INTO v_max_id FROM mol_bronze.chembl_activities_nonpart;
    IF v_max_id = 0 THEN
        RETURN;  -- empty table, nothing to copy
    END IF;
    WHILE v_low < v_max_id LOOP
        INSERT INTO mol_bronze.chembl_activities
        SELECT * FROM mol_bronze.chembl_activities_nonpart
        WHERE id > v_low AND id <= v_low + v_chunk;
        v_low := v_low + v_chunk;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;
END $$;

COMMIT;

-- Step 3: Execute the chunked copy (each batch auto-commits inside the procedure)
CALL _tmp_partition_copy_chembl_activities();

-- Step 4: Cleanup
BEGIN;
DROP TABLE mol_bronze.chembl_activities_nonpart;
DROP PROCEDURE _tmp_partition_copy_chembl_activities();
COMMIT;

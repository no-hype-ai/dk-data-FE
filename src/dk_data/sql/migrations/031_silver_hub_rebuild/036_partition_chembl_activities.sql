-- Migration 031/036_partition_chembl_activities.sql: Partition mol_bronze.chembl_activities by month
-- Feature: 001-silver-medallion-rebuild / T163-T167
--
-- On fresh deploy (CI), the bronze table doesn't exist yet (created by SQLMesh).
-- On existing clusters, renames → partitions → copies data in chunks → drops old.

-- Create procedure that handles everything including chunked copy with per-batch COMMIT.
CREATE OR REPLACE PROCEDURE _partition_chembl_activities()
LANGUAGE plpgsql AS $$
DECLARE
    v_max_id BIGINT;
    v_low    BIGINT := 0;
    v_chunk  CONSTANT BIGINT := 50000;
BEGIN
    -- Guard: skip if table doesn't exist (fresh deploy)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_bronze' AND table_name = 'chembl_activities'
    ) THEN
        RAISE NOTICE 'mol_bronze.chembl_activities does not exist — skipping';
        RETURN;
    END IF;

    -- Guard: skip if already partitioned
    IF EXISTS (
        SELECT 1 FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'mol_bronze' AND c.relname = 'chembl_activities'
    ) THEN
        RAISE NOTICE 'mol_bronze.chembl_activities already partitioned — skipping';
        RETURN;
    END IF;

    -- Step 1: Rename
    ALTER TABLE mol_bronze.chembl_activities RENAME TO chembl_activities_nonpart;

    -- Step 2: Create partitioned parent
    CREATE TABLE mol_bronze.chembl_activities (
        LIKE mol_bronze.chembl_activities_nonpart INCLUDING DEFAULTS INCLUDING CONSTRAINTS
    ) PARTITION BY RANGE (ingested_at);

    CREATE TABLE mol_bronze.chembl_activities_y2024m01 PARTITION OF mol_bronze.chembl_activities FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
    CREATE TABLE mol_bronze.chembl_activities_y2024m06 PARTITION OF mol_bronze.chembl_activities FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');
    CREATE TABLE mol_bronze.chembl_activities_y2025m01 PARTITION OF mol_bronze.chembl_activities FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
    CREATE TABLE mol_bronze.chembl_activities_y2025m06 PARTITION OF mol_bronze.chembl_activities FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
    CREATE TABLE mol_bronze.chembl_activities_y2026m01 PARTITION OF mol_bronze.chembl_activities FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
    CREATE TABLE mol_bronze.chembl_activities_default PARTITION OF mol_bronze.chembl_activities DEFAULT;
    COMMIT;

    -- Step 3: Chunked data copy (each batch commits independently)
    SELECT COALESCE(MAX(id), 0) INTO v_max_id FROM mol_bronze.chembl_activities_nonpart;
    WHILE v_low < v_max_id LOOP
        INSERT INTO mol_bronze.chembl_activities
        SELECT * FROM mol_bronze.chembl_activities_nonpart
        WHERE id > v_low AND id <= v_low + v_chunk;
        v_low := v_low + v_chunk;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;

    -- Step 4: Cleanup + BRIN
    DROP TABLE mol_bronze.chembl_activities_nonpart;
    CREATE INDEX IF NOT EXISTS idx_chembl_activities_ingested_brin
        ON mol_bronze.chembl_activities USING BRIN (ingested_at) WITH (pages_per_range = 128);
    COMMIT;
END $$;

-- Execute (requires autocommit — migration runner detects CALL and enables it)
CALL _partition_chembl_activities();

-- Cleanup procedure
DROP PROCEDURE IF EXISTS _partition_chembl_activities();

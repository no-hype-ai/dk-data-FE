-- Migration 031/038_partition_clinicaltrials.sql: Partition mol_bronze.clinicaltrials by month
-- Feature: 001-silver-medallion-rebuild / T163-T167

CREATE OR REPLACE PROCEDURE _partition_clinicaltrials()
LANGUAGE plpgsql AS $$
DECLARE
    v_max_id BIGINT;
    v_low    BIGINT := 0;
    v_chunk  CONSTANT BIGINT := 50000;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_bronze' AND table_name = 'clinicaltrials'
    ) THEN
        RAISE NOTICE 'mol_bronze.clinicaltrials does not exist — skipping';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'mol_bronze' AND c.relname = 'clinicaltrials'
    ) THEN
        RAISE NOTICE 'mol_bronze.clinicaltrials already partitioned — skipping';
        RETURN;
    END IF;

    -- Guard: skip if id column is not bigint (legacy table from migration 020 with UUID ids;
    -- SQLMesh will replace it with the correct schema)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_bronze' AND table_name = 'clinicaltrials'
          AND column_name = 'id' AND data_type = 'bigint'
    ) THEN
        RAISE NOTICE 'mol_bronze.clinicaltrials has non-bigint id — skipping (legacy table)';
        RETURN;
    END IF;

    ALTER TABLE mol_bronze.clinicaltrials RENAME TO clinicaltrials_nonpart;

    CREATE TABLE mol_bronze.clinicaltrials (
        LIKE mol_bronze.clinicaltrials_nonpart INCLUDING DEFAULTS INCLUDING CONSTRAINTS
    ) PARTITION BY RANGE (ingested_at);

    CREATE TABLE mol_bronze.clinicaltrials_y2024m01 PARTITION OF mol_bronze.clinicaltrials FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
    CREATE TABLE mol_bronze.clinicaltrials_y2024m06 PARTITION OF mol_bronze.clinicaltrials FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');
    CREATE TABLE mol_bronze.clinicaltrials_y2025m01 PARTITION OF mol_bronze.clinicaltrials FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
    CREATE TABLE mol_bronze.clinicaltrials_y2025m06 PARTITION OF mol_bronze.clinicaltrials FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
    CREATE TABLE mol_bronze.clinicaltrials_y2026m01 PARTITION OF mol_bronze.clinicaltrials FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
    CREATE TABLE mol_bronze.clinicaltrials_default PARTITION OF mol_bronze.clinicaltrials DEFAULT;
    COMMIT;

    SELECT COALESCE(MAX(id), 0) INTO v_max_id FROM mol_bronze.clinicaltrials_nonpart;
    WHILE v_low < v_max_id LOOP
        INSERT INTO mol_bronze.clinicaltrials
        SELECT * FROM mol_bronze.clinicaltrials_nonpart
        WHERE id > v_low AND id <= v_low + v_chunk;
        v_low := v_low + v_chunk;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;

    DROP TABLE mol_bronze.clinicaltrials_nonpart;
    CREATE INDEX IF NOT EXISTS idx_clinicaltrials_ingested_brin
        ON mol_bronze.clinicaltrials USING BRIN (ingested_at) WITH (pages_per_range = 128);
    COMMIT;
END $$;

CALL _partition_clinicaltrials();

DROP PROCEDURE IF EXISTS _partition_clinicaltrials();

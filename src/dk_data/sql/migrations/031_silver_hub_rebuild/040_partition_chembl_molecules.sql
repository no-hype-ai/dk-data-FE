-- Migration 031/040_partition_chembl_molecules.sql: Partition mol_bronze.chembl_molecules by month
-- Feature: 001-silver-medallion-rebuild / T163-T167

CREATE OR REPLACE PROCEDURE _partition_chembl_molecules()
LANGUAGE plpgsql AS $$
DECLARE
    v_max_id BIGINT;
    v_low    BIGINT := 0;
    v_chunk  CONSTANT BIGINT := 50000;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_bronze' AND table_name = 'chembl_molecules'
    ) THEN
        RAISE NOTICE 'mol_bronze.chembl_molecules does not exist — skipping';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'mol_bronze' AND c.relname = 'chembl_molecules'
    ) THEN
        RAISE NOTICE 'mol_bronze.chembl_molecules already partitioned — skipping';
        RETURN;
    END IF;

    ALTER TABLE mol_bronze.chembl_molecules RENAME TO chembl_molecules_nonpart;

    CREATE TABLE mol_bronze.chembl_molecules (
        LIKE mol_bronze.chembl_molecules_nonpart INCLUDING DEFAULTS INCLUDING CONSTRAINTS
    ) PARTITION BY RANGE (ingested_at);

    CREATE TABLE mol_bronze.chembl_molecules_y2024m01 PARTITION OF mol_bronze.chembl_molecules FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
    CREATE TABLE mol_bronze.chembl_molecules_y2024m06 PARTITION OF mol_bronze.chembl_molecules FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');
    CREATE TABLE mol_bronze.chembl_molecules_y2025m01 PARTITION OF mol_bronze.chembl_molecules FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
    CREATE TABLE mol_bronze.chembl_molecules_y2025m06 PARTITION OF mol_bronze.chembl_molecules FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
    CREATE TABLE mol_bronze.chembl_molecules_y2026m01 PARTITION OF mol_bronze.chembl_molecules FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
    CREATE TABLE mol_bronze.chembl_molecules_default PARTITION OF mol_bronze.chembl_molecules DEFAULT;
    COMMIT;

    SELECT COALESCE(MAX(id), 0) INTO v_max_id FROM mol_bronze.chembl_molecules_nonpart;
    WHILE v_low < v_max_id LOOP
        INSERT INTO mol_bronze.chembl_molecules
        SELECT * FROM mol_bronze.chembl_molecules_nonpart
        WHERE id > v_low AND id <= v_low + v_chunk;
        v_low := v_low + v_chunk;
        COMMIT;
        PERFORM pg_sleep(0.05);
    END LOOP;

    DROP TABLE mol_bronze.chembl_molecules_nonpart;
    CREATE INDEX IF NOT EXISTS idx_chembl_molecules_ingested_brin
        ON mol_bronze.chembl_molecules USING BRIN (ingested_at) WITH (pages_per_range = 128);
    COMMIT;
END $$;

CALL _partition_chembl_molecules();

DROP PROCEDURE IF EXISTS _partition_chembl_molecules();

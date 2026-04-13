-- Minimum fixture dataset for dk-data-client integration tests.
-- Idempotent: each run truncates + reinserts the rows below.
--
-- Tables touched:
--   mol_silver.molecules          (hub)
--   mol_silver.molecule_identifiers
--   mol_silver.molecule_names
--   mol_gold.molecule_profile     (gold view/table)
--   ind_silver.conditions
--   mol_silver.companies
--
-- Known molecules (used by integration tests):
--   CHEMBL25    — Aspirin
--   CHEMBL112   — Paracetamol / Acetaminophen
--   CHEMBL521   — Caffeine
--
-- Everything fits inside one transaction so a failure leaves the
-- database clean.

BEGIN;

SET LOCAL statement_timeout = '30s';

-- Ensure schemas exist (the real dk-data already has them, but integration
-- fixtures may run against a fresh Postgres container).
CREATE SCHEMA IF NOT EXISTS mol_silver;
CREATE SCHEMA IF NOT EXISTS mol_gold;
CREATE SCHEMA IF NOT EXISTS ind_silver;

-- Only touch fixture tables. Do NOT truncate any table that might
-- carry real data — even in a test DB, assume someone may have loaded
-- non-fixture rows alongside.
DELETE FROM mol_silver.molecules
WHERE molecule_id IN ('CHEMBL25', 'CHEMBL112', 'CHEMBL521');

INSERT INTO mol_silver.molecules (molecule_id, canonical_name, inchi_key, created_at)
VALUES
    ('CHEMBL25',  'Aspirin',      'BSYNRYMUTXBXSQ-UHFFFAOYSA-N', NOW()),
    ('CHEMBL112', 'Paracetamol',  'RZVAJINKPMORJF-UHFFFAOYSA-N', NOW()),
    ('CHEMBL521', 'Caffeine',     'RYYVLZVUVIJVGH-UHFFFAOYSA-N', NOW());

-- Condition fixture for ind_silver.conditions
DELETE FROM ind_silver.conditions
WHERE condition_id IN ('C0011849', 'C0013604');

INSERT INTO ind_silver.conditions (condition_id, canonical_name, icd10, mesh, created_at)
VALUES
    ('C0011849', 'Diabetes Mellitus',   'E11', 'D003924', NOW()),
    ('C0013604', 'Edema',               'R60', 'D004487', NOW());

-- Optional molecule_profile fixture — some rows already in the gold
-- layer will carry through, this just adds the fixture-specific ones.
-- If mol_gold.molecule_profile doesn't exist in the fixture DB, this
-- migration is a no-op.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_gold' AND table_name = 'molecule_profile'
    ) THEN
        EXECUTE 'DELETE FROM mol_gold.molecule_profile WHERE molecule_id IN (''CHEMBL25'', ''CHEMBL112'', ''CHEMBL521'')';
        EXECUTE 'INSERT INTO mol_gold.molecule_profile (molecule_id, canonical_name, max_phase, active_trials, computed_at) VALUES
            (''CHEMBL25'',  ''Aspirin'',      4, 42, NOW()),
            (''CHEMBL112'', ''Paracetamol'',  4, 15, NOW()),
            (''CHEMBL521'', ''Caffeine'',     4,  8, NOW())';
    END IF;
END $$;

COMMIT;

-- Migration 157: GIN indexes on mol_raw response_body columns (item 4)
-- Post-backfill performance improvement. Each mol_raw table now holds millions
-- of rows; bronze models filter heavily on response_body JSONB keys/values.
-- GIN indexes accelerate JSONB containment (@>) and key-exist (?) operators.
--
-- Each index is guarded with an existence check so this migration is safe to
-- run even when a table hasn't been created yet (e.g. in CI or fresh installs).
-- On a live production cluster with large tables, you can recreate CONCURRENTLY:
--   DROP INDEX IF EXISTS idx_mol_raw_pubchem_body_gin;
--   CREATE INDEX CONCURRENTLY idx_mol_raw_pubchem_body_gin ON mol_raw.pubchem USING gin(response_body);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_raw' AND tablename = 'pubchem') THEN
    CREATE INDEX IF NOT EXISTS idx_mol_raw_pubchem_body_gin ON mol_raw.pubchem USING gin(response_body);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_raw' AND tablename = 'chembl_molecules') THEN
    CREATE INDEX IF NOT EXISTS idx_mol_raw_chembl_molecules_body_gin ON mol_raw.chembl_molecules USING gin(response_body);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_raw' AND tablename = 'bindingdb') THEN
    CREATE INDEX IF NOT EXISTS idx_mol_raw_bindingdb_body_gin ON mol_raw.bindingdb USING gin(response_body);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_raw' AND tablename = 'sider') THEN
    CREATE INDEX IF NOT EXISTS idx_mol_raw_sider_body_gin ON mol_raw.sider USING gin(response_body);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_raw' AND tablename = 'uniprot') THEN
    CREATE INDEX IF NOT EXISTS idx_mol_raw_uniprot_body_gin ON mol_raw.uniprot USING gin(response_body);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_raw' AND tablename = 'openfda_labels') THEN
    CREATE INDEX IF NOT EXISTS idx_mol_raw_openfda_labels_body_gin ON mol_raw.openfda_labels USING gin(response_body);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_raw' AND tablename = 'pdb') THEN
    CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_body_gin ON mol_raw.pdb USING gin(response_body);
  END IF;
END $$;

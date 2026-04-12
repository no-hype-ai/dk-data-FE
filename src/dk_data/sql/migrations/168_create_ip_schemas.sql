-- Migration 050: Create ip_* domain schemas
-- Part of: 001-silver-medallion-rebuild (FR-006a)
-- Creates ip_raw, ip_bronze, ip_silver, ip_gold schemas + PostgREST role grants

BEGIN;

CREATE SCHEMA IF NOT EXISTS ip_raw;
CREATE SCHEMA IF NOT EXISTS ip_bronze;
CREATE SCHEMA IF NOT EXISTS ip_silver;
CREATE SCHEMA IF NOT EXISTS ip_gold;

-- PostgREST role grants (same pattern as mol_* schemas)
DO $$ BEGIN
  -- Revoke public access from consumer-facing schemas
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
    REVOKE ALL ON SCHEMA ip_silver FROM web_anon;
    REVOKE ALL ON SCHEMA ip_gold FROM web_anon;
  END IF;

  -- Grant analyst role access to consumer-facing schemas
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
    GRANT USAGE ON SCHEMA ip_raw TO analyst;
    GRANT USAGE ON SCHEMA ip_bronze TO analyst;
    GRANT USAGE ON SCHEMA ip_silver TO analyst;
    GRANT USAGE ON SCHEMA ip_gold TO analyst;
  END IF;

  -- Grant mol_data_ops access (data operations role)
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
    GRANT USAGE ON SCHEMA ip_raw TO mol_data_ops;
    GRANT USAGE ON SCHEMA ip_bronze TO mol_data_ops;
    GRANT USAGE ON SCHEMA ip_silver TO mol_data_ops;
    GRANT USAGE ON SCHEMA ip_gold TO mol_data_ops;
    GRANT CREATE ON SCHEMA ip_raw TO mol_data_ops;
    GRANT CREATE ON SCHEMA ip_bronze TO mol_data_ops;
    GRANT CREATE ON SCHEMA ip_silver TO mol_data_ops;
    GRANT CREATE ON SCHEMA ip_gold TO mol_data_ops;
  END IF;

  -- Grant mol_admin full access
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_admin') THEN
    GRANT ALL ON SCHEMA ip_raw TO mol_admin;
    GRANT ALL ON SCHEMA ip_bronze TO mol_admin;
    GRANT ALL ON SCHEMA ip_silver TO mol_admin;
    GRANT ALL ON SCHEMA ip_gold TO mol_admin;
  END IF;
END $$;

COMMIT;

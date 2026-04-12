-- Migration 054: PostgREST grants for ip_silver and ip_gold schemas
-- Part of: 001-silver-medallion-rebuild (T110r)
-- GRANT SELECT on all current and future tables in ip_silver.* and ip_gold.* to analyst, mol_data_ops, mol_admin.
--
-- NOTE: After data migration verification is complete, revoke mol_silver grants for migrated tables:
--   REVOKE SELECT ON mol_silver.patents FROM analyst, mol_data_ops, mol_admin;
--   REVOKE SELECT ON mol_silver.trademarks FROM analyst, mol_data_ops, mol_admin;
--   REVOKE SELECT ON mol_silver.patent_exclusivities FROM analyst, mol_data_ops, mol_admin;
--   REVOKE SELECT ON mol_silver.trademark_status_changes FROM analyst, mol_data_ops, mol_admin;
--   REVOKE SELECT ON mol_silver.euipo_designs FROM analyst, mol_data_ops, mol_admin;

BEGIN;

DO $$ BEGIN

  -- ============================================================
  -- analyst role — read-only access to ip_silver and ip_gold
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN

    -- ip_silver: grant on existing tables + default privileges for future tables
    GRANT SELECT ON ALL TABLES IN SCHEMA ip_silver TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_silver GRANT SELECT ON TABLES TO analyst;

    -- ip_gold: grant on existing tables + default privileges for future tables
    GRANT SELECT ON ALL TABLES IN SCHEMA ip_gold TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_gold GRANT SELECT ON TABLES TO analyst;

    RAISE NOTICE 'Granted ip_silver + ip_gold SELECT to analyst';
  END IF;

  -- ============================================================
  -- mol_data_ops role — read/write access to all ip_* schemas
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN

    -- ip_raw
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ip_raw TO mol_data_ops;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_raw GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mol_data_ops;

    -- ip_bronze
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ip_bronze TO mol_data_ops;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_bronze GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mol_data_ops;

    -- ip_silver
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ip_silver TO mol_data_ops;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_silver GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mol_data_ops;

    -- ip_gold
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ip_gold TO mol_data_ops;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_gold GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mol_data_ops;

    RAISE NOTICE 'Granted ip_* read/write to mol_data_ops';
  END IF;

  -- ============================================================
  -- mol_admin role — full access to all ip_* schemas
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_admin') THEN

    GRANT ALL ON ALL TABLES IN SCHEMA ip_raw TO mol_admin;
    GRANT ALL ON ALL TABLES IN SCHEMA ip_bronze TO mol_admin;
    GRANT ALL ON ALL TABLES IN SCHEMA ip_silver TO mol_admin;
    GRANT ALL ON ALL TABLES IN SCHEMA ip_gold TO mol_admin;

    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_raw GRANT ALL ON TABLES TO mol_admin;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_bronze GRANT ALL ON TABLES TO mol_admin;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_silver GRANT ALL ON TABLES TO mol_admin;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ip_gold GRANT ALL ON TABLES TO mol_admin;

    RAISE NOTICE 'Granted ip_* ALL to mol_admin';
  END IF;

  -- ============================================================
  -- web_anon — explicitly no access (belt + suspenders)
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA ip_silver FROM web_anon;
    REVOKE ALL ON ALL TABLES IN SCHEMA ip_gold FROM web_anon;
    REVOKE ALL ON ALL TABLES IN SCHEMA ip_bronze FROM web_anon;
    REVOKE ALL ON ALL TABLES IN SCHEMA ip_raw FROM web_anon;
    RAISE NOTICE 'Revoked ip_* access from web_anon';
  END IF;

END $$;

COMMIT;

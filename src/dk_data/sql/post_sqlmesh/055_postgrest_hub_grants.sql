-- Migration 055: PostgREST role permissions for new hub, crosswalk, and name-index tables
-- Part of: 001-silver-medallion-rebuild (T145)
--
-- Hub tables are created by SQLMesh. On first deploy they may not exist yet.
-- Each GRANT block is wrapped in an exception handler that skips gracefully
-- if the target table does not exist. Grants will succeed on next deploy
-- after SQLMesh has materialized the tables.

BEGIN;

DO $$ BEGIN

  -- ============================================================
  -- web_anon role — REMOVED by feature 002-external-integration-foundation
  -- US-2 (migration 218_drop_web_anon.sql). The legacy anonymous read
  -- role is no longer granted here. Every PostgREST request now requires
  -- a valid JWT (enforced by `authenticator` role switching to a
  -- JWT-supplied role). The IF EXISTS check is kept below as a defense-
  -- in-depth guard — if `web_anon` somehow reappears, the old broad
  -- grants are NOT reapplied; instead the script raises a loud warning
  -- so operators can investigate.
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
    RAISE WARNING
      'web_anon role exists but should have been dropped by migration 218 (feature 002-external-integration-foundation US-2). Investigate — this role must not be re-granted on silver hub tables.';
  END IF;

  -- ============================================================
  -- analyst role — full silver/gold read access
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
    -- GRANT ON ALL TABLES IN SCHEMA is safe even if schema is empty
    GRANT SELECT ON ALL TABLES IN SCHEMA mol_silver TO analyst;
    GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO analyst;
    GRANT SELECT ON ALL TABLES IN SCHEMA ind_silver TO analyst;
    GRANT SELECT ON ALL TABLES IN SCHEMA hcp_silver TO analyst;

    ALTER DEFAULT PRIVILEGES IN SCHEMA mol_silver GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA hcs_silver GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ind_silver GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA hcp_silver GRANT SELECT ON TABLES TO analyst;

    RAISE NOTICE 'Granted all silver schema SELECT to analyst';
  END IF;

  -- ============================================================
  -- mol_viewer role — limited read access (if role exists)
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_viewer') THEN
    BEGIN
      GRANT SELECT ON TABLE
          mol_silver.molecules, mol_silver.molecule_identifiers, mol_silver.molecule_names,
          mol_silver.drug_products, mol_silver.drug_product_identifiers, mol_silver.drug_product_names,
          mol_silver.companies, mol_silver.company_names,
          mol_silver.targets, mol_silver.target_names
      TO mol_viewer;
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'Skipping mol_silver hub grants to mol_viewer (tables not yet created by SQLMesh)';
    END;
  END IF;

  -- ============================================================
  -- T013: mol_silver.atc_classifications — ATC hierarchy table
  -- Part of: 006-claims-engine-data-gaps
  -- mol_silver is already in PGRST_DB_SCHEMAS; grants follow the
  -- same exception-wrapped pattern as above.
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
    BEGIN
      GRANT SELECT ON TABLE mol_silver.atc_classifications TO analyst;
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'Skipping mol_silver.atc_classifications grant to analyst (table not yet created by SQLMesh)';
    END;
  END IF;

  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_viewer') THEN
    BEGIN
      GRANT SELECT ON TABLE mol_silver.atc_classifications TO mol_viewer;
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'Skipping mol_silver.atc_classifications grant to mol_viewer (table not yet created by SQLMesh)';
    END;
  END IF;

  -- ============================================================
  -- T076: mol_silver.fda_enforcement_actions — unified enforcement table
  -- Part of: 006-claims-engine-data-gaps
  -- Already covered by schema-wide GRANT / ALTER DEFAULT PRIVILEGES
  -- above; explicit grant here ensures coverage even if table was
  -- created outside the default-privilege session.
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
    BEGIN
      GRANT SELECT ON TABLE mol_silver.fda_enforcement_actions TO analyst;
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'Skipping mol_silver.fda_enforcement_actions grant to analyst (table not yet created by SQLMesh)';
    END;
  END IF;

  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_viewer') THEN
    BEGIN
      GRANT SELECT ON TABLE mol_silver.fda_enforcement_actions TO mol_viewer;
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'Skipping mol_silver.fda_enforcement_actions grant to mol_viewer (table not yet created by SQLMesh)';
    END;
  END IF;

END $$;

COMMIT;

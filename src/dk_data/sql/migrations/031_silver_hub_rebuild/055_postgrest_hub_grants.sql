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
  -- web_anon role — read-only public API access
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
    BEGIN
      GRANT SELECT ON TABLE
          mol_silver.molecules, mol_silver.molecule_identifiers, mol_silver.molecule_names,
          mol_silver.drug_products, mol_silver.drug_product_identifiers, mol_silver.drug_product_names, mol_silver.drug_product_ingredients,
          mol_silver.companies, mol_silver.company_identifiers, mol_silver.company_names,
          mol_silver.targets, mol_silver.target_identifiers, mol_silver.target_names, mol_silver.target_sequences
      TO web_anon;
    EXCEPTION WHEN undefined_table THEN
      RAISE NOTICE 'Skipping mol_silver hub grants to web_anon (tables not yet created by SQLMesh)';
    END;

    BEGIN
      GRANT SELECT ON TABLE
          hcs_silver.providers, hcs_silver.provider_identifiers, hcs_silver.provider_names,
          hcs_silver.facilities, hcs_silver.facility_identifiers, hcs_silver.facility_names
      TO web_anon;
    EXCEPTION WHEN undefined_table THEN
      RAISE NOTICE 'Skipping hcs_silver hub grants to web_anon (tables not yet created by SQLMesh)';
    END;

    BEGIN
      GRANT SELECT ON TABLE
          ind_silver.conditions, ind_silver.condition_identifiers, ind_silver.condition_names
      TO web_anon;
    EXCEPTION WHEN undefined_table THEN
      RAISE NOTICE 'Skipping ind_silver hub grants to web_anon (tables not yet created by SQLMesh)';
    END;

    BEGIN
      GRANT SELECT ON TABLE
          hcp_silver.researchers, hcp_silver.researcher_identifiers, hcp_silver.researcher_names
      TO web_anon;
    EXCEPTION WHEN undefined_table THEN
      RAISE NOTICE 'Skipping hcp_silver hub grants to web_anon (tables not yet created by SQLMesh)';
    END;

    BEGIN
      GRANT SELECT ON TABLE
          ip_silver.patents, ip_silver.patent_identifiers, ip_silver.patent_names,
          ip_silver.trademarks, ip_silver.trademark_identifiers, ip_silver.trademark_names,
          ip_silver.designs, ip_silver.design_identifiers, ip_silver.design_names
      TO web_anon;
    EXCEPTION WHEN undefined_table THEN
      RAISE NOTICE 'Skipping ip_silver hub grants to web_anon (tables not yet created by SQLMesh)';
    END;

    RAISE NOTICE 'Processed hub table SELECT grants for web_anon';
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
    EXCEPTION WHEN undefined_table THEN
      RAISE NOTICE 'Skipping mol_silver hub grants to mol_viewer (tables not yet created by SQLMesh)';
    END;
  END IF;

END $$;

COMMIT;

-- Migration 055: PostgREST role permissions for new hub, crosswalk, and name-index tables
-- Part of: 001-silver-medallion-rebuild (T145)
--
-- Grants SELECT on all hub, identifier crosswalk, and name-index tables created in
-- Phase 4 (Wave 3) to the PostgREST reader roles web_anon and analyst.
--
-- New tables covered:
--   mol_silver: molecules, molecule_identifiers, molecule_names,
--               drug_products, drug_product_identifiers, drug_product_names, drug_product_ingredients,
--               companies, company_identifiers, company_names,
--               targets, target_identifiers, target_names, target_sequences
--   hcs_silver: providers, provider_identifiers, provider_names,
--               facilities, facility_identifiers, facility_names
--   ind_silver: conditions, condition_identifiers, condition_names
--   hcp_silver: researchers, researcher_identifiers, researcher_names (if present)
--   ip_silver:  patents, patent_identifiers, patent_names,
--               trademarks, trademark_identifiers, trademark_names,
--               designs, design_identifiers, design_names

BEGIN;

DO $$ BEGIN

  -- ============================================================
  -- web_anon role — read-only public API access (short timeout enforced in migration 041)
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN

    -- mol_silver hub tables
    GRANT SELECT ON TABLE
        mol_silver.molecules,
        mol_silver.molecule_identifiers,
        mol_silver.molecule_names,
        mol_silver.drug_products,
        mol_silver.drug_product_identifiers,
        mol_silver.drug_product_names,
        mol_silver.drug_product_ingredients,
        mol_silver.companies,
        mol_silver.company_identifiers,
        mol_silver.company_names,
        mol_silver.targets,
        mol_silver.target_identifiers,
        mol_silver.target_names,
        mol_silver.target_sequences
    TO web_anon;

    -- hcs_silver hub tables
    GRANT SELECT ON TABLE
        hcs_silver.providers,
        hcs_silver.provider_identifiers,
        hcs_silver.provider_names,
        hcs_silver.facilities,
        hcs_silver.facility_identifiers,
        hcs_silver.facility_names
    TO web_anon;

    -- ind_silver hub tables
    GRANT SELECT ON TABLE
        ind_silver.conditions,
        ind_silver.condition_identifiers,
        ind_silver.condition_names
    TO web_anon;

    -- ip_silver hub tables
    GRANT SELECT ON TABLE
        ip_silver.patents,
        ip_silver.patent_identifiers,
        ip_silver.patent_names,
        ip_silver.trademarks,
        ip_silver.trademark_identifiers,
        ip_silver.trademark_names,
        ip_silver.designs,
        ip_silver.design_identifiers,
        ip_silver.design_names
    TO web_anon;

    RAISE NOTICE 'Granted hub table SELECT to web_anon';
  END IF;

  -- ============================================================
  -- analyst role — full silver/gold read access (5 min timeout)
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN

    -- Grant SELECT on all current tables in new hub schemas
    -- (ip_silver already covered by migration 054)
    GRANT SELECT ON ALL TABLES IN SCHEMA mol_silver TO analyst;
    GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO analyst;
    GRANT SELECT ON ALL TABLES IN SCHEMA ind_silver TO analyst;
    GRANT SELECT ON ALL TABLES IN SCHEMA hcp_silver TO analyst;

    -- Future tables in each schema
    ALTER DEFAULT PRIVILEGES IN SCHEMA mol_silver GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA hcs_silver GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA ind_silver GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA hcp_silver GRANT SELECT ON TABLES TO analyst;

    RAISE NOTICE 'Granted all silver schema SELECT to analyst (including new hub tables)';
  END IF;

  -- ============================================================
  -- mol_viewer role — limited read access (if role exists)
  -- ============================================================
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_viewer') THEN

    GRANT SELECT ON TABLE
        mol_silver.molecules,
        mol_silver.molecule_identifiers,
        mol_silver.molecule_names,
        mol_silver.drug_products,
        mol_silver.drug_product_identifiers,
        mol_silver.drug_product_names,
        mol_silver.companies,
        mol_silver.company_names,
        mol_silver.targets,
        mol_silver.target_names
    TO mol_viewer;

    RAISE NOTICE 'Granted core hub table SELECT to mol_viewer';
  END IF;

END $$;

COMMIT;

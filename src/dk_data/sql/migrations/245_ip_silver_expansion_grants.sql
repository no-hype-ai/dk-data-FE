-- Migration 245: Ensure ip_silver grants cover new expansion models (T058)
-- Feature: 006-claims-engine-data-gaps (Item 28)
-- Re-applies default privileges for ip_silver to cover patent_families,
-- patent_citations, and trademark_oppositions created by T069-T071.
-- Migration 210 already set ALTER DEFAULT PRIVILEGES, but this ensures
-- any tables created outside that session also get covered.

BEGIN;

DO $$ BEGIN

  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
    GRANT SELECT ON ALL TABLES IN SCHEMA ip_silver TO analyst;
    RAISE NOTICE 'Re-granted ip_silver SELECT to analyst';
  END IF;

  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ip_silver TO mol_data_ops;
    RAISE NOTICE 'Re-granted ip_silver read/write to mol_data_ops';
  END IF;

  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_admin') THEN
    GRANT ALL ON ALL TABLES IN SCHEMA ip_silver TO mol_admin;
    RAISE NOTICE 'Re-granted ip_silver ALL to mol_admin';
  END IF;

END $$;

COMMIT;

-- Migration 097: Grant authenticator + analyst access to mol_gold, mol_silver, xenon, meta
--
-- PostgREST connects as 'authenticator' then switches to JWT-specified roles.
-- The authenticator role needs USAGE on all exposed schemas, and each role
-- needs appropriate table grants.

-- authenticator needs USAGE on all schemas PostgREST exposes
DO $$
DECLARE
    v_schema TEXT;
BEGIN
    FOREACH v_schema IN ARRAY ARRAY['mol_gold', 'mol_silver', 'xenon', 'meta'] LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = v_schema) THEN
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO authenticator', v_schema);
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO analyst', v_schema);
            EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO analyst', v_schema);
        END IF;
    END LOOP;
END $$;

-- analyst can write to xenon tables (assessment generation)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'xenon') THEN
        EXECUTE 'GRANT INSERT ON ALL TABLES IN SCHEMA xenon TO analyst';
    END IF;
END $$;

-- Migration: 167_role_session_defaults.sql
-- Set session-level PostgreSQL parameters on the application role.
-- These replace the invalid session_properties in SQLMesh config.yaml
-- (SQLMesh 0.230.0 postgres connector does not support session_properties).
--
-- work_mem = 128MB   — half the per-session ceiling (256MB), leaves headroom for hash joins
-- statement_timeout  — 10 min hard cap prevents runaway queries
-- idle_in_transaction_session_timeout — 5 min cap releases locks from idle sessions

BEGIN;

DO $$
DECLARE
    v_role text;
BEGIN
    -- Detect the current role (works whether it's 'postgres', 'dk_data', or custom)
    v_role := current_user;

    EXECUTE format('ALTER ROLE %I SET work_mem = %L', v_role, '128MB');
    EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', v_role, '600000');
    EXECUTE format('ALTER ROLE %I SET idle_in_transaction_session_timeout = %L', v_role, '300000');

    RAISE NOTICE 'Set session defaults on role %: work_mem=128MB, statement_timeout=10min, idle_in_tx=5min', v_role;
END $$;

COMMIT;

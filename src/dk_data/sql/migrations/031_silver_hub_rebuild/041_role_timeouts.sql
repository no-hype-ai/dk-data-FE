-- Migration 031/041: Per-role statement_timeout and idle_in_transaction_session_timeout
-- Feature: 001-silver-medallion-rebuild / T180

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        ALTER ROLE web_anon SET statement_timeout = '30s';
        ALTER ROLE web_anon SET idle_in_transaction_session_timeout = '60s';
    END IF;

    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        ALTER ROLE analyst SET statement_timeout = '5min';
        ALTER ROLE analyst SET idle_in_transaction_session_timeout = '5min';
    END IF;

    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_admin') THEN
        ALTER ROLE mol_admin SET statement_timeout = '1h';
        ALTER ROLE mol_admin SET idle_in_transaction_session_timeout = '30min';
    END IF;

    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        ALTER ROLE mol_data_ops SET statement_timeout = '30min';
        ALTER ROLE mol_data_ops SET idle_in_transaction_session_timeout = '10min';
    END IF;
END $$;

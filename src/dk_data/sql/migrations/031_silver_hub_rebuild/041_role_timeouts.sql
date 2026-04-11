-- Migration 031/041: Per-role statement_timeout and idle_in_transaction_session_timeout
-- Feature: 001-silver-medallion-rebuild / T180
--
-- Sets conservative timeouts per role to prevent runaway queries and idle connections.
--   web_anon:    30s statement, 60s idle (public API — short-lived anonymous queries)
--   analyst:     5min statement, 5min idle (interactive analysis)
--   mol_admin:   1h statement, 30min idle (admin/maintenance operations)
--   mol_data_ops: 30min statement, 10min idle (data pipeline operations)

-- web_anon: anonymous API access — aggressive timeouts for safety
ALTER ROLE web_anon
    SET statement_timeout = '30s'
    SET idle_in_transaction_session_timeout = '60s';

-- analyst: interactive BI/exploration — moderate timeouts
ALTER ROLE analyst
    SET statement_timeout = '5min'
    SET idle_in_transaction_session_timeout = '5min';

-- mol_admin: administrative role — generous timeouts for maintenance
ALTER ROLE mol_admin
    SET statement_timeout = '1h'
    SET idle_in_transaction_session_timeout = '30min';

-- mol_data_ops: data pipeline role — long enough for bulk ops but bounded
ALTER ROLE mol_data_ops
    SET statement_timeout = '30min'
    SET idle_in_transaction_session_timeout = '10min';

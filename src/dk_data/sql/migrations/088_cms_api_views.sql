-- Migration 088: CMS API Views and Permissions (016-cms-puf-datasource-integration)
--
-- API views wrap gold views for PostgREST exposure.
-- PostgREST serves from the api schema; these thin wrappers decouple
-- the public contract from the gold-layer implementation.

BEGIN;

-- ─── API Views ────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW api.cms_provider_profile AS
SELECT * FROM hcs_gold.cms_provider_360;

CREATE OR REPLACE VIEW api.cms_facility_profile AS
SELECT * FROM hcs_gold.cms_facility_360;

CREATE OR REPLACE VIEW api.cms_drug_market AS
SELECT * FROM hcs_gold.cms_drug_market_profile;

CREATE OR REPLACE VIEW api.cms_market_analytics AS
SELECT * FROM hcs_gold.cms_market_analytics;

CREATE OR REPLACE VIEW api.cms_provider_network AS
SELECT * FROM hcs_gold.cms_provider_network;

-- ─── API View Permissions ─────────────────────────────────────────────────────

GRANT SELECT ON api.cms_provider_profile   TO analyst, api_user;
GRANT SELECT ON api.cms_facility_profile   TO analyst, api_user;
GRANT SELECT ON api.cms_drug_market        TO analyst, api_user;
GRANT SELECT ON api.cms_market_analytics   TO analyst, api_user;
GRANT SELECT ON api.cms_provider_network   TO analyst, api_user;

-- ─── Gold Schema Access ──────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA gold TO analyst, api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO analyst, api_user;

COMMIT;

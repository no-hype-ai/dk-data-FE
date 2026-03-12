-- Migration 093: API wrappers for per-source data-tools gold views
--
-- Extends 088 (composite API views) with thin wrappers for the 17
-- per-source gold views created in 092. This keeps the api schema as
-- the stable public contract for PostgREST consumers.
--
-- Note: gold schema already has GRANT SELECT … TO analyst, api_user
-- from migration 088 (line 37-38), so we only need the api.* views.

BEGIN;

-- ─── Drug / HCPCS keyed ────────────────────────────────────────────────────
CREATE OR REPLACE VIEW api.cms_part_d_spending AS SELECT * FROM gold.cms_part_d_spending;
CREATE OR REPLACE VIEW api.cms_part_b_spending AS SELECT * FROM gold.cms_part_b_spending;
CREATE OR REPLACE VIEW api.cms_formulary       AS SELECT * FROM gold.cms_formulary;
CREATE OR REPLACE VIEW api.cms_ndc             AS SELECT * FROM gold.cms_ndc;
CREATE OR REPLACE VIEW api.cms_rbcs            AS SELECT * FROM gold.cms_rbcs;
CREATE OR REPLACE VIEW api.cms_nucc            AS SELECT * FROM gold.cms_nucc;
CREATE OR REPLACE VIEW api.cms_usp             AS SELECT * FROM gold.cms_usp;
CREATE OR REPLACE VIEW api.cms_stabilis        AS SELECT * FROM gold.cms_stabilis;
CREATE OR REPLACE VIEW api.cms_ddinter         AS SELECT * FROM gold.cms_ddinter;

-- ─── Facility / CCN keyed ──────────────────────────────────────────────────
CREATE OR REPLACE VIEW api.cms_chow                 AS SELECT * FROM gold.cms_chow;
CREATE OR REPLACE VIEW api.cms_hospital_affiliation AS SELECT * FROM gold.cms_hospital_affiliation;
CREATE OR REPLACE VIEW api.cms_post_acute           AS SELECT * FROM gold.cms_post_acute;
CREATE OR REPLACE VIEW api.cms_pos                  AS SELECT * FROM gold.cms_pos;
CREATE OR REPLACE VIEW api.cms_hcris                AS SELECT * FROM gold.cms_hcris;
CREATE OR REPLACE VIEW api.cms_magnet               AS SELECT * FROM gold.cms_magnet;

-- ─── Provider / NPI keyed ──────────────────────────────────────────────────
CREATE OR REPLACE VIEW api.cms_nppes  AS SELECT * FROM gold.cms_nppes;
CREATE OR REPLACE VIEW api.cms_dmepos AS SELECT * FROM gold.cms_dmepos;

-- ─── Permissions ───────────────────────────────────────────────────────────
GRANT SELECT ON api.cms_part_d_spending        TO analyst, api_user;
GRANT SELECT ON api.cms_part_b_spending        TO analyst, api_user;
GRANT SELECT ON api.cms_formulary              TO analyst, api_user;
GRANT SELECT ON api.cms_ndc                    TO analyst, api_user;
GRANT SELECT ON api.cms_rbcs                   TO analyst, api_user;
GRANT SELECT ON api.cms_nucc                   TO analyst, api_user;
GRANT SELECT ON api.cms_usp                    TO analyst, api_user;
GRANT SELECT ON api.cms_stabilis               TO analyst, api_user;
GRANT SELECT ON api.cms_ddinter                TO analyst, api_user;
GRANT SELECT ON api.cms_chow                   TO analyst, api_user;
GRANT SELECT ON api.cms_hospital_affiliation   TO analyst, api_user;
GRANT SELECT ON api.cms_post_acute             TO analyst, api_user;
GRANT SELECT ON api.cms_pos                    TO analyst, api_user;
GRANT SELECT ON api.cms_hcris                  TO analyst, api_user;
GRANT SELECT ON api.cms_magnet                 TO analyst, api_user;
GRANT SELECT ON api.cms_nppes                  TO analyst, api_user;
GRANT SELECT ON api.cms_dmepos                 TO analyst, api_user;

COMMIT;

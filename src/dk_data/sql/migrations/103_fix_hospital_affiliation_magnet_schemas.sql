-- Migration 103: Fix schema mismatches for cms_hospital_affiliation and cms_magnet.
-- The fetchers were rewritten to use the actual CMS Provider Data API and ANCC
-- Magnet Excel download, producing different fields than the original tables.
--
-- Part of: 016-cms-puf-datasource-integration

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. hcs_raw.cms_hospital_affiliation — fetcher now uses CMS Provider Data API
--    dataset 27ea-46a8 which returns provider-level affiliation records.
--    Old schema: (affiliation_id PK, npi, ccn, affiliation_type)
--    New schema: matches fetcher output from _normalise()
-- ═══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS hcs_gold.cms_hospital_affiliation CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hospital_affiliation CASCADE;

CREATE TABLE hcs_raw.cms_hospital_affiliation (
    npi                                     TEXT NOT NULL,
    ind_pac_id                              TEXT,
    provider_last_name                      TEXT,
    provider_first_name                     TEXT,
    provider_middle_name                    TEXT,
    suff                                    TEXT,
    facility_type                           TEXT,
    facility_affiliations_certification_number TEXT,
    facility_type_certification_number      TEXT,
    _loaded_at                              TIMESTAMPTZ DEFAULT now(),
    _source_file                            TEXT,
    _source_hash                            TEXT,
    PRIMARY KEY (npi, facility_affiliations_certification_number)
);

CREATE INDEX IF NOT EXISTS idx_cms_hospital_affiliation_npi
    ON hcs_raw.cms_hospital_affiliation (npi);

CREATE OR REPLACE VIEW hcs_gold.cms_hospital_affiliation AS
SELECT
    npi,
    ind_pac_id,
    provider_last_name,
    provider_first_name,
    provider_middle_name,
    facility_type,
    facility_affiliations_certification_number,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_hospital_affiliation;


-- ═══════════════════════════════════════════════════════════════════════════
-- 2. hcs_raw.cms_magnet — fetcher now downloads Excel from ANCC with fields:
--    facility_name, city, state, country, zip_code, designation_year,
--    redesignation_years, web_address.
--    Old schema: (facility_id PK, facility_name, city, state,
--                 designation_date, expiration_date)
-- ═══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS hcs_gold.cms_magnet CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_magnet CASCADE;

CREATE TABLE hcs_raw.cms_magnet (
    facility_name                           TEXT NOT NULL,
    city                                    TEXT,
    state                                   TEXT NOT NULL,
    country                                 TEXT,
    zip_code                                TEXT,
    designation_year                        TEXT,
    redesignation_years                     TEXT,
    web_address                             TEXT,
    _loaded_at                              TIMESTAMPTZ DEFAULT now(),
    _source_file                            TEXT,
    _source_hash                            TEXT,
    PRIMARY KEY (facility_name, state)
);

CREATE OR REPLACE VIEW hcs_gold.cms_magnet AS
SELECT
    facility_name,
    city,
    state,
    country,
    zip_code,
    designation_year,
    redesignation_years,
    web_address,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_magnet;

COMMIT;

-- Migration 134: CREATE TABLE IF NOT EXISTS for 4 legacy hcs_raw tables
--
-- These tables were created manually or by early loaders before the migration
-- system tracked DDL. Migration 099 (_safe_move_schema) only moves tables that
-- already exist in raw.* — silently skips if the source doesn't exist. On a
-- fresh cluster there is no raw.* baseline, so these 4 tables were never created.
--
-- Loaders that write to these tables:
--   hcs_raw.acc_tvc_certification    <- sources/acc_tvc.py
--   hcs_raw.cms_cost_reports         <- sources/cms_cost_reports.py
--   hcs_raw.cms_hospital_info        <- sources/cms_hospital_info.py
--   hcs_raw.cms_medicare_inpatient   <- sources/cms_inpatient.py
--
-- Column lists are derived from the INSERT statements in each loader.
-- All tables follow the standard hcs_raw pattern:
--   id BIGSERIAL PK, operational columns, _loaded_at, _source_hash.
-- Ref: issue #172 S5

CREATE TABLE IF NOT EXISTS hcs_raw.acc_tvc_certification (
    id                  BIGSERIAL       PRIMARY KEY,
    facility_name       TEXT            NOT NULL,
    facility_address    TEXT,
    city                TEXT,
    state               TEXT,
    zip_code            TEXT,
    certification_type  TEXT,
    certification_date  DATE,
    expiration_date     DATE,
    _source_file        TEXT,
    _source_hash        TEXT,
    _loaded_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_cost_reports (
    id                          BIGSERIAL   PRIMARY KEY,
    provider_id                 TEXT        NOT NULL,
    fiscal_year_begin           DATE,
    fiscal_year_end             DATE,
    total_beds                  INTEGER,
    total_discharges            INTEGER,
    net_patient_revenue         NUMERIC,
    total_operating_expenses    NUMERIC,
    operating_margin            NUMERIC,
    _source_hash                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_info (
    id                      BIGSERIAL   PRIMARY KEY,
    provider_id             TEXT        NOT NULL,
    hospital_name           TEXT,
    address                 TEXT,
    city                    TEXT,
    state                   TEXT,
    zip_code                TEXT,
    county_name             TEXT,
    phone_number            TEXT,
    hospital_type           TEXT,
    hospital_ownership      TEXT,
    emergency_services      BOOLEAN,
    hospital_overall_rating TEXT,
    _source_hash            TEXT,
    _loaded_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_medicare_inpatient (
    id                          BIGSERIAL   PRIMARY KEY,
    provider_id                 TEXT        NOT NULL,
    provider_name               TEXT,
    provider_street_address     TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip_code           TEXT,
    drg_code                    TEXT        NOT NULL,
    drg_description             TEXT,
    total_discharges            INTEGER,
    average_covered_charges     NUMERIC,
    average_total_payments      NUMERIC,
    average_medicare_payments   NUMERIC,
    fiscal_year                 INTEGER     NOT NULL,
    _source_file                TEXT,
    _source_hash                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, fiscal_year, drg_code)
);

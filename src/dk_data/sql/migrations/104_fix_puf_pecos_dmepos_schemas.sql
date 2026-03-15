-- Migration 104: Fix schema mismatches for CMS PUF, PECOS, DMEPOS, and
-- Geographic Variation tables.
-- The CMS data-api datasets do not include a year column — the dataset UUID
-- implicitly represents one year. Remove year from PKs and make nullable.
-- Also fix column names to match actual API field names.
--
-- Part of: 016-cms-puf-datasource-integration

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. raw.cms_dmepos — API returns supplier-level summary, not per-HCPCS.
--    Actual fields: Suplr_NPI, Tot_Suplr_Srvcs, Tot_Suplr_Benes, etc.
--    Drop hcpcs_code from PK, make year nullable.
-- ═══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS gold.cms_dmepos CASCADE;
DROP TABLE IF EXISTS raw.cms_dmepos CASCADE;

CREATE TABLE raw.cms_dmepos (
    npi                     TEXT NOT NULL,
    hcpcs_code              TEXT,
    hcpcs_description       TEXT,
    total_services          TEXT,
    total_beneficiaries     TEXT,
    avg_submitted_charge    TEXT,
    avg_medicare_payment    TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (npi)
);

CREATE OR REPLACE VIEW gold.cms_dmepos AS
SELECT npi, total_services, total_beneficiaries,
       avg_submitted_charge, avg_medicare_payment,
       _loaded_at AS last_refreshed
FROM raw.cms_dmepos;


-- ═══════════════════════════════════════════════════════════════════════════
-- 2. raw.cms_inpatient_puf — API has no year column. Remove year from PK.
-- ═══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS gold.cms_inpatient_puf CASCADE;
ALTER TABLE raw.cms_inpatient_puf DROP CONSTRAINT IF EXISTS cms_inpatient_puf_pkey;
ALTER TABLE raw.cms_inpatient_puf ALTER COLUMN year DROP NOT NULL;
ALTER TABLE raw.cms_inpatient_puf
    ADD CONSTRAINT cms_inpatient_puf_pkey PRIMARY KEY (provider_id, drg_code);


-- ═══════════════════════════════════════════════════════════════════════════
-- 3. raw.cms_outpatient_puf — API uses APC_Cd not HCPCS_Cd, no year.
--    Recreate with correct column names.
-- ═══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS gold.cms_outpatient_puf CASCADE;
DROP TABLE IF EXISTS raw.cms_outpatient_puf CASCADE;

CREATE TABLE raw.cms_outpatient_puf (
    provider_id             TEXT NOT NULL,
    apc_code                TEXT NOT NULL,
    apc_description         TEXT,
    total_services          TEXT,
    avg_submitted_charges   TEXT,
    avg_total_payments      TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (provider_id, apc_code)
);

CREATE OR REPLACE VIEW gold.cms_outpatient_puf AS
SELECT provider_id, apc_code, apc_description,
       total_services, avg_submitted_charges, avg_total_payments,
       _loaded_at AS last_refreshed
FROM raw.cms_outpatient_puf;


-- ═══════════════════════════════════════════════════════════════════════════
-- 4. raw.cms_physician_puf — range-partitioned by year.
--    Cannot remove year from PK (Postgres requires partition key in PK).
--    Instead, default year to 0 so fetcher output without year still inserts.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE raw.cms_physician_puf ALTER COLUMN year SET DEFAULT 0;


-- ═══════════════════════════════════════════════════════════════════════════
-- 5. raw.cms_geographic_variation — county can be NULL for national rows.
--    Change PK to (state, year) and allow NULL county.
-- ═══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS gold.cms_geographic_variation CASCADE;
ALTER TABLE raw.cms_geographic_variation DROP CONSTRAINT IF EXISTS cms_geographic_variation_pkey;
ALTER TABLE raw.cms_geographic_variation ALTER COLUMN county DROP NOT NULL;
ALTER TABLE raw.cms_geographic_variation ALTER COLUMN year DROP NOT NULL;
ALTER TABLE raw.cms_geographic_variation
    ADD CONSTRAINT cms_geographic_variation_pkey PRIMARY KEY (state);

CREATE OR REPLACE VIEW gold.cms_geographic_variation AS
SELECT state, county, bene_count, total_actual_costs, per_capita_costs,
       year, _loaded_at AS last_refreshed
FROM raw.cms_geographic_variation;


-- ═══════════════════════════════════════════════════════════════════════════
-- 6. raw.cms_pecos — Recreate with correct API field names.
--    API returns: NPI, ENRLMT_ID, ORG_NAME, PROVIDER_TYPE_DESC, STATE_CD
-- ═══════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS gold.cms_pecos CASCADE;
DROP TABLE IF EXISTS raw.cms_pecos CASCADE;

CREATE TABLE raw.cms_pecos (
    npi                     TEXT NOT NULL,
    enrollment_id           TEXT,
    organization_name       TEXT,
    state                   TEXT,
    enrollment_type         TEXT,
    first_name              TEXT,
    last_name               TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (npi)
);

CREATE OR REPLACE VIEW gold.cms_pecos AS
SELECT npi, enrollment_id, organization_name, state, enrollment_type,
       first_name, last_name, _loaded_at AS last_refreshed
FROM raw.cms_pecos;

COMMIT;

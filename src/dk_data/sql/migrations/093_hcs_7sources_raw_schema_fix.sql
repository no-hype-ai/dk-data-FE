-- =============================================================================
-- Migration 093: HCS 7-Source Raw Table Schema Fix
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
-- =============================================================================
-- Rebuilds 7 hcs_raw tables to use exact snake_case of CMS raw API field names.
-- Migration 085 used aliased/renamed columns that diverge from what the Python
-- loaders now write after the column-name audit in this feature.
--
-- Sources fixed:
--   1. cms_chronic_conditions  — was: bene_geo_cd/prevalence/total_medicare_payment
--                                now: bene_geo_cd/bene_cond/prvlnc/tot_mdcr_stdzd_pymt_pc/etc.
--   2. cms_dual_eligible       — was: state/dual_benes/non_dual_benes
--                                now: state_cd/dual_elgbl_lvl/tot_benes/ffs_benes/etc.
--   3. cms_enrollment_puf      — was: state/county/fips/total_beneficiaries/aged_esrd_benes
--                                now: state_cd/county_cd/county_desc/bene_demo_lvl/etc.
--   4. cms_utilization_puf     — was: service_category/setting_of_care/total_services
--                                now: bene_geo_lvl/bene_geo_cd/srvcs_per_bene/etc.
--   5. cms_claim_type_puf      — was: claim_type/service_category/total_claims
--                                now: bene_geo_lvl/clm_type/tot_clms/avg_mdcr_pymt_amt/etc.
--   6. cms_referring_providers — was: referring_npi/referred_to_npi (missing provider detail)
--                                now: rndrng_npi/rfrd_npi + full provider columns
--   7. cms_ordering_providers  — was: ordering_npi/performing_npi (wrong field names)
--                                now: rndrng_npi/rfrd_npi + full provider columns
--
-- Strategy: DROP + RECREATE with IF NOT EXISTS for indexes.
-- ROLLBACK: see 093_rollback.sql
-- Run: doppler run -- python -m dk_data.scripts.run_migration src/dk_data/sql/migrations/093_hcs_7sources_raw_schema_fix.sql
-- =============================================================================

BEGIN;

-- ============================================================================
-- 1. cms_chronic_conditions
--    CMS raw fields: Bene_Geo_Lvl, Bene_Geo_Desc, Bene_Geo_Cd, Bene_Age_Lvl,
--    Bene_Demo_Lvl, Bene_Demo_Desc, Bene_Cond, Prvlnc,
--    Tot_Mdcr_Stdzd_Pymt_PC, Tot_Mdcr_Pymt_PC, Hosp_Readmsn_Rate,
--    ED_Visits_Per_1000_Benes
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_chronic_conditions CASCADE;

CREATE TABLE hcs_raw.cms_chronic_conditions (
    id                          BIGSERIAL PRIMARY KEY,
    -- Geography (TEXT — geo codes include leading zeros like state FIPS)
    bene_geo_lvl                TEXT,           -- 'National', 'State', 'County'
    bene_geo_desc               TEXT,
    bene_geo_cd                 TEXT,           -- FIPS or state abbreviation (TEXT)
    -- Stratification dimensions
    bene_age_lvl                TEXT,
    bene_demo_lvl               TEXT,
    bene_demo_desc              TEXT,
    -- Condition and prevalence
    bene_cond                   TEXT,
    prvlnc                      NUMERIC(10,4),  -- rate 0-1
    -- Medicare payment per capita
    tot_mdcr_stdzd_pymt_pc      NUMERIC(18,2),
    tot_mdcr_pymt_pc            NUMERIC(18,2),
    -- Utilization rates
    hosp_readmsn_rate            NUMERIC(10,4),
    ed_visits_per_1000_benes     NUMERIC(10,4),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bene_geo_cd, bene_age_lvl, bene_cond, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_chronic_conditions_geo
    ON hcs_raw.cms_chronic_conditions (bene_geo_cd);
CREATE INDEX IF NOT EXISTS idx_cms_chronic_conditions_year
    ON hcs_raw.cms_chronic_conditions (_source_year);
CREATE INDEX IF NOT EXISTS idx_cms_chronic_conditions_cond
    ON hcs_raw.cms_chronic_conditions (bene_cond);

-- ============================================================================
-- 2. cms_dual_eligible
--    CMS raw fields: State_Cd, State_Name, Dual_Elgbl_Lvl, Dual_Elgbl_Desc,
--    Tot_Benes, FFS_Benes, MA_Benes, Dual_Elgbl_Full_Benes,
--    Dual_Elgbl_Prtl_Benes, Non_Dual_Benes, LIS_Benes
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_dual_eligible CASCADE;

CREATE TABLE hcs_raw.cms_dual_eligible (
    id                          BIGSERIAL PRIMARY KEY,
    -- Geography (TEXT — state codes are 2-char abbreviations)
    state_cd                    TEXT,
    state_name                  TEXT,
    -- Dual eligibility stratification
    dual_elgbl_lvl              TEXT,
    dual_elgbl_desc             TEXT,
    -- Beneficiary counts (INTEGER — whole person counts)
    tot_benes                   INTEGER,
    ffs_benes                   INTEGER,
    ma_benes                    INTEGER,
    dual_elgbl_full_benes       INTEGER,
    dual_elgbl_prtl_benes       INTEGER,
    non_dual_benes              INTEGER,
    lis_benes                   INTEGER,
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (state_cd, dual_elgbl_lvl, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_dual_eligible_state
    ON hcs_raw.cms_dual_eligible (state_cd);
CREATE INDEX IF NOT EXISTS idx_cms_dual_eligible_year
    ON hcs_raw.cms_dual_eligible (_source_year);

-- ============================================================================
-- 3. cms_enrollment_puf
--    CMS raw fields: State_Cd, County_Cd, County_Desc, Bene_Demo_Lvl,
--    Bene_Demo_Desc, Bene_Age_Lvl, Tot_Benes, Orgnl_Mdcr_Benes,
--    MA_Benes, ESRD_Benes, Dsbl_Benes
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_enrollment_puf CASCADE;

CREATE TABLE hcs_raw.cms_enrollment_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Geography (TEXT — county codes and state codes have leading zeros)
    state_cd                    TEXT,
    county_cd                   TEXT,
    county_desc                 TEXT,
    -- Stratification dimensions
    bene_demo_lvl               TEXT,
    bene_demo_desc              TEXT,
    bene_age_lvl                TEXT,
    -- Beneficiary counts (INTEGER — whole person counts)
    tot_benes                   INTEGER,
    orgnl_mdcr_benes            INTEGER,
    ma_benes                    INTEGER,
    esrd_benes                  INTEGER,
    dsbl_benes                  INTEGER,
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (state_cd, county_cd, bene_demo_lvl, bene_age_lvl, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_enrollment_puf_state
    ON hcs_raw.cms_enrollment_puf (state_cd);
CREATE INDEX IF NOT EXISTS idx_cms_enrollment_puf_county
    ON hcs_raw.cms_enrollment_puf (county_cd);
CREATE INDEX IF NOT EXISTS idx_cms_enrollment_puf_year
    ON hcs_raw.cms_enrollment_puf (_source_year);

-- ============================================================================
-- 4. cms_utilization_puf
--    CMS raw fields: Bene_Geo_Lvl, Bene_Geo_Desc, Bene_Geo_Cd, Bene_Age_Lvl,
--    Bene_Demo_Lvl, Bene_Demo_Desc, Srvcs_Per_Bene,
--    IP_Cvrd_Stays_Per_1000_Benes, Avg_IP_LOS,
--    ER_Visits_Per_1000_Benes, Phy_Visits_Per_Bene, Tot_Mdcr_Pymt_PC
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_utilization_puf CASCADE;

CREATE TABLE hcs_raw.cms_utilization_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Geography (TEXT — geo codes include leading zeros)
    bene_geo_lvl                TEXT,
    bene_geo_desc               TEXT,
    bene_geo_cd                 TEXT,
    -- Stratification dimensions
    bene_age_lvl                TEXT,
    bene_demo_lvl               TEXT,
    bene_demo_desc              TEXT,
    -- Utilization rates (NUMERIC — rates per beneficiary or per 1000)
    srvcs_per_bene              NUMERIC(10,4),
    ip_cvrd_stays_per_1000_benes NUMERIC(10,4),
    avg_ip_los                  NUMERIC(10,4),
    er_visits_per_1000_benes     NUMERIC(10,4),
    phy_visits_per_bene          NUMERIC(10,4),
    -- Payment per capita (NUMERIC)
    tot_mdcr_pymt_pc            NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bene_geo_cd, bene_age_lvl, bene_demo_lvl, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_utilization_puf_geo
    ON hcs_raw.cms_utilization_puf (bene_geo_cd);
CREATE INDEX IF NOT EXISTS idx_cms_utilization_puf_year
    ON hcs_raw.cms_utilization_puf (_source_year);

-- ============================================================================
-- 5. cms_claim_type_puf
--    CMS raw fields: Bene_Geo_Lvl, Bene_Geo_Desc, Clm_Type, Clm_Type_Desc,
--    Tot_Clms, Tot_Benes, Tot_Mdcr_Pymt_Amt, Avg_Mdcr_Pymt_Amt
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_claim_type_puf CASCADE;

CREATE TABLE hcs_raw.cms_claim_type_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Geography (TEXT)
    bene_geo_lvl                TEXT,
    bene_geo_desc               TEXT,
    -- Claim type dimension
    clm_type                    TEXT,
    clm_type_desc               TEXT,
    -- Volume counts (INTEGER — whole claim/beneficiary counts)
    tot_clms                    BIGINT,
    tot_benes                   INTEGER,
    -- Payment amounts (NUMERIC)
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bene_geo_lvl, clm_type, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_claim_type_puf_clm_type
    ON hcs_raw.cms_claim_type_puf (clm_type);
CREATE INDEX IF NOT EXISTS idx_cms_claim_type_puf_year
    ON hcs_raw.cms_claim_type_puf (_source_year);

-- ============================================================================
-- 6. cms_referring_providers
--    CMS raw fields: Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name,
--    Rndrng_Prvdr_First_Name, Rndrng_Prvdr_City, Rndrng_Prvdr_State_Abrvtn,
--    Rndrng_Prvdr_Zip5, Rndrng_Prvdr_Type,
--    Rfrd_NPI, Rfrd_Prvdr_Last_Org_Name, Rfrd_Prvdr_Type,
--    Tot_Srvcs, Tot_Benes, Tot_Mdcr_Alowd_Amt, Tot_Mdcr_Pymt_Amt
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_referring_providers CASCADE;

CREATE TABLE hcs_raw.cms_referring_providers (
    id                          BIGSERIAL PRIMARY KEY,
    -- Rendering (receiving) provider identifiers (NPI as TEXT — 10-digit string)
    rndrng_npi                  TEXT,
    rndrng_prvdr_last_org_name  TEXT,
    rndrng_prvdr_first_name     TEXT,
    rndrng_prvdr_city           TEXT,
    rndrng_prvdr_state_abrvtn   TEXT,
    rndrng_prvdr_zip5           TEXT,           -- ZIP as TEXT (leading zeros)
    rndrng_prvdr_type           TEXT,
    -- Referred-from (referring) provider identifiers (NPI as TEXT)
    rfrd_npi                    TEXT,
    rfrd_prvdr_last_org_name    TEXT,
    rfrd_prvdr_type             TEXT,
    -- Volume and payment metrics
    tot_srvcs                   NUMERIC(18,2),
    tot_benes                   INTEGER,
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rndrng_npi, rfrd_npi, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_referring_providers_rndrng_npi
    ON hcs_raw.cms_referring_providers (rndrng_npi);
CREATE INDEX IF NOT EXISTS idx_cms_referring_providers_rfrd_npi
    ON hcs_raw.cms_referring_providers (rfrd_npi);
CREATE INDEX IF NOT EXISTS idx_cms_referring_providers_year
    ON hcs_raw.cms_referring_providers (_source_year);

-- ============================================================================
-- 7. cms_ordering_providers
--    CMS raw fields: Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name,
--    Rndrng_Prvdr_First_Name, Rndrng_Prvdr_City, Rndrng_Prvdr_State_Abrvtn,
--    Rndrng_Prvdr_Zip5, Rndrng_Prvdr_Type,
--    Rfrd_NPI, Rfrd_Prvdr_Last_Org_Name, Rfrd_Prvdr_Type,
--    Tot_Srvcs, Tot_Benes, Tot_Mdcr_Alowd_Amt, Tot_Mdcr_Pymt_Amt
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_ordering_providers CASCADE;

CREATE TABLE hcs_raw.cms_ordering_providers (
    id                          BIGSERIAL PRIMARY KEY,
    -- Ordering provider identifiers (NPI as TEXT — 10-digit string)
    rndrng_npi                  TEXT,
    rndrng_prvdr_last_org_name  TEXT,
    rndrng_prvdr_first_name     TEXT,
    rndrng_prvdr_city           TEXT,
    rndrng_prvdr_state_abrvtn   TEXT,
    rndrng_prvdr_zip5           TEXT,           -- ZIP as TEXT (leading zeros)
    rndrng_prvdr_type           TEXT,
    -- Referred-to (ordered for) provider identifiers (NPI as TEXT)
    rfrd_npi                    TEXT,
    rfrd_prvdr_last_org_name    TEXT,
    rfrd_prvdr_type             TEXT,
    -- Volume and payment metrics
    tot_srvcs                   NUMERIC(18,2),
    tot_benes                   INTEGER,
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rndrng_npi, rfrd_npi, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_ordering_providers_rndrng_npi
    ON hcs_raw.cms_ordering_providers (rndrng_npi);
CREATE INDEX IF NOT EXISTS idx_cms_ordering_providers_rfrd_npi
    ON hcs_raw.cms_ordering_providers (rfrd_npi);
CREATE INDEX IF NOT EXISTS idx_cms_ordering_providers_year
    ON hcs_raw.cms_ordering_providers (_source_year);

-- ============================================================================
-- 8. Re-grant web_anon and analyst access (tables were dropped + recreated)
-- ============================================================================

GRANT SELECT ON hcs_raw.cms_chronic_conditions   TO web_anon;
GRANT SELECT ON hcs_raw.cms_dual_eligible         TO web_anon;
GRANT SELECT ON hcs_raw.cms_enrollment_puf        TO web_anon;
GRANT SELECT ON hcs_raw.cms_utilization_puf       TO web_anon;
GRANT SELECT ON hcs_raw.cms_claim_type_puf        TO web_anon;
GRANT SELECT ON hcs_raw.cms_referring_providers   TO web_anon;
GRANT SELECT ON hcs_raw.cms_ordering_providers    TO web_anon;

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        GRANT SELECT ON hcs_raw.cms_chronic_conditions   TO analyst;
        GRANT SELECT ON hcs_raw.cms_dual_eligible         TO analyst;
        GRANT SELECT ON hcs_raw.cms_enrollment_puf        TO analyst;
        GRANT SELECT ON hcs_raw.cms_utilization_puf       TO analyst;
        GRANT SELECT ON hcs_raw.cms_claim_type_puf        TO analyst;
        GRANT SELECT ON hcs_raw.cms_referring_providers   TO analyst;
        GRANT SELECT ON hcs_raw.cms_ordering_providers    TO analyst;
    END IF;
END
$$;

COMMIT;

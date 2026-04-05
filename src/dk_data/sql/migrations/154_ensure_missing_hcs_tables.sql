-- Migration 154: Ensure hcs_raw tables that may be absent in prod
-- Migration 150 was marked applied on some instances but the table was never
-- actually created (DB restored after migration tracking was written).
-- Re-create with IF NOT EXISTS to be idempotent.

CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber (
    id                      BIGSERIAL PRIMARY KEY,
    prscrbr_npi             TEXT        NOT NULL,
    prscrbr_last_org_name   TEXT,
    prscrbr_first_name      TEXT,
    prscrbr_city            TEXT,
    prscrbr_state_abrvtn    TEXT,
    prscrbr_state_fips      TEXT,
    prscrbr_type            TEXT,
    prscrbr_type_src        TEXT,
    brnd_name               TEXT,
    gnrc_name               TEXT        NOT NULL,
    tot_clms                INTEGER,
    tot_30day_fills         TEXT,
    tot_day_suply           INTEGER,
    tot_drug_cst            TEXT,
    tot_benes               INTEGER,
    ge65_sprsn_flag         TEXT,
    ge65_tot_clms           INTEGER,
    ge65_tot_30day_fills    TEXT,
    ge65_tot_drug_cst       TEXT,
    ge65_tot_day_suply      INTEGER,
    ge65_bene_sprsn_flag    TEXT,
    ge65_tot_benes          INTEGER,
    _source_year            INTEGER,
    _source_hash            TEXT,
    _source_file            TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS cms_part_d_prescriber_npi_drug_year_uniq
    ON hcs_raw.cms_part_d_prescriber (prscrbr_npi, gnrc_name, _source_year);

COMMENT ON TABLE hcs_raw.cms_part_d_prescriber IS
    'CMS Medicare Part D Prescribers by Provider and Drug. Source: data.cms.gov. Grain: NPI x generic drug name x year.';

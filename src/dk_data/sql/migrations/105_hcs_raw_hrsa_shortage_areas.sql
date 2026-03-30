-- Migration 105: Create hcs_raw.hrsa_shortage_areas table
-- HRSA Health Professional Shortage Area (HPSA) designations.
-- Loaded from bulk CSV: https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv

CREATE TABLE IF NOT EXISTS hcs_raw.hrsa_shortage_areas (
    id                  BIGSERIAL PRIMARY KEY,
    hpsa_id             TEXT,
    hpsa_name           TEXT,
    hpsa_type           TEXT,       -- 'Primary Care', 'Mental Health', 'Dental Health'
    designation_type    TEXT,
    state_abbr          TEXT,
    county_name         TEXT,
    hpsa_score          INTEGER,    -- 0-25 (higher = more severe shortage)
    designation_date    DATE,
    rural_status        TEXT,       -- 'Rural', 'Urban', etc.
    _source_hash        TEXT,
    _fetched_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hrsa_shortage_state
    ON hcs_raw.hrsa_shortage_areas (state_abbr);

CREATE INDEX IF NOT EXISTS idx_hrsa_shortage_type
    ON hcs_raw.hrsa_shortage_areas (hpsa_type);

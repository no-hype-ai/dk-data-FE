-- Migration 107: Fix formulary table to match CMS basic drugs formulary file
-- Applied: 2026-03-15
--
-- The CMS formulary ZIP contains pipe-delimited TXT files with columns:
-- FORMULARY_ID, FORMULARY_VERSION, CONTRACT_YEAR, RXCUI, NDC,
-- TIER_LEVEL_VALUE, QUANTITY_LIMIT_YN, QUANTITY_LIMIT_AMOUNT,
-- QUANTITY_LIMIT_DAYS, PRIOR_AUTHORIZATION_YN, STEP_THERAPY_YN
--
-- contract_id and plan_id are in a separate "plan information" file,
-- not in the basic drugs formulary. PK changed to (formulary_id, rxcui).

DROP TABLE IF EXISTS raw.cms_formulary CASCADE;
CREATE TABLE raw.cms_formulary (
    formulary_id         TEXT NOT NULL,
    rxcui                TEXT NOT NULL,
    ndc                  TEXT,
    tier_level           TEXT,
    prior_auth           TEXT,
    step_therapy         TEXT,
    quantity_limit       TEXT,
    quantity_limit_amount TEXT,
    quantity_limit_days  TEXT,
    _loaded_at           TIMESTAMPTZ DEFAULT now(),
    _source_file         TEXT,
    _source_hash         TEXT,
    PRIMARY KEY (formulary_id, rxcui)
);

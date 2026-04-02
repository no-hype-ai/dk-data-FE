-- Migration: 143_mart_scoring_stubs_api_targets
-- Purpose: Create stub mart/scoring tables required by api.targets view.
--          These tables are populated by the TAVR hospital pipeline in production.
--          In local dev and CI, they exist as empty stubs so api.targets resolves.

BEGIN;

-- mart schema stubs
CREATE TABLE IF NOT EXISTS mart.dim_hospital (
    hospital_key    SERIAL PRIMARY KEY,
    hospital_id     TEXT NOT NULL UNIQUE,
    hospital_name   TEXT,
    health_system_name TEXT,
    network_tier    TEXT,
    state           TEXT,
    city            TEXT,
    county          TEXT,
    hospital_type   TEXT,
    ownership_type  TEXT,
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mart.fact_tavr_program (
    id                      SERIAL PRIMARY KEY,
    hospital_key            INTEGER REFERENCES mart.dim_hospital(hospital_key),
    fiscal_year             INTEGER,
    estimated_total_volume  INTEGER,
    tvt_star_rating         NUMERIC(3,1)
);

-- scoring schema stubs
CREATE TABLE IF NOT EXISTS scoring.target_scores (
    id                          SERIAL PRIMARY KEY,
    hospital_key                INTEGER REFERENCES mart.dim_hospital(hospital_key),
    total_trs                   NUMERIC(5,2),
    tier_classification         TEXT,
    clinical_readiness_score    NUMERIC(5,2),
    operational_readiness_score NUMERIC(5,2),
    strategic_alignment_score   NUMERIC(5,2),
    financial_capacity_score    NUMERIC(5,2),
    champion_access_score       NUMERIC(5,2),
    data_completeness           NUMERIC(5,2),
    score_date                  DATE NOT NULL DEFAULT CURRENT_DATE
);

-- api.targets view
CREATE OR REPLACE VIEW api.targets AS
SELECT
    h.hospital_id,
    h.hospital_name,
    h.health_system_name,
    h.network_tier,
    h.state,
    h.city,
    s.total_trs,
    s.tier_classification,
    s.clinical_readiness_score,
    s.operational_readiness_score,
    s.strategic_alignment_score,
    s.financial_capacity_score,
    s.champion_access_score,
    s.data_completeness,
    s.score_date,
    f.estimated_total_volume AS latest_tavr_volume,
    f.tvt_star_rating
FROM mart.dim_hospital h
JOIN scoring.target_scores s ON h.hospital_key = s.hospital_key
LEFT JOIN mart.fact_tavr_program f ON h.hospital_key = f.hospital_key
    AND f.fiscal_year = (
        SELECT MAX(fiscal_year) FROM mart.fact_tavr_program WHERE hospital_key = h.hospital_key
    )
WHERE h.is_current = TRUE
  AND s.score_date = (
      SELECT MAX(score_date) FROM scoring.target_scores WHERE hospital_key = s.hospital_key
  );

-- Role grants
GRANT USAGE ON SCHEMA mart, scoring TO analyst, api_user, authenticator;
GRANT SELECT ON mart.dim_hospital, mart.fact_tavr_program TO analyst, api_user;
GRANT SELECT ON scoring.target_scores TO analyst, api_user;
GRANT SELECT ON api.targets TO analyst, api_user;
-- web_anon must NOT have SELECT on api.targets (auth-protected view)
REVOKE SELECT ON api.targets FROM web_anon;

DO $$ BEGIN
    RAISE NOTICE 'Migration 143 complete: mart/scoring stubs + api.targets view created.';
END $$;

COMMIT;

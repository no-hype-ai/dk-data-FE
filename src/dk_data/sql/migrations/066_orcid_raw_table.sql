-- Migration 066: ORCID raw table
-- Feature: 012-platform-hardening (US3)

CREATE TABLE IF NOT EXISTS raw.orcid (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    orcid_id VARCHAR(30) NOT NULL UNIQUE,
    given_names VARCHAR(255),
    family_name VARCHAR(255),
    credit_name VARCHAR(500),
    biography TEXT,
    keywords JSONB,
    current_affiliations JSONB,
    works_count INTEGER,
    external_ids JSONB,
    raw_response JSONB,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orcid_id ON raw.orcid(orcid_id);
CREATE INDEX IF NOT EXISTS idx_orcid_family ON raw.orcid(family_name);

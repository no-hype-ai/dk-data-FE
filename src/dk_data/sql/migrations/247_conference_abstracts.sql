-- Migration 247: mol_raw.conference_abstracts
-- Conference abstract data scraped from major medical conferences.
-- Feature: 006-claims-engine-data-gaps (T077)

BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.conference_abstracts (
    id                    BIGSERIAL PRIMARY KEY,
    abstract_id           TEXT,
    conference_name       TEXT,
    conference_body       TEXT,
    conference_date       DATE,
    presentation_date     DATE,
    presentation_type     TEXT,
    title                 TEXT,
    authors               JSONB,
    affiliations          JSONB,
    abstract_text         TEXT,
    embargo_date          DATE,
    publication_date      DATE,
    session_title         TEXT,
    track                 TEXT,
    source_url            TEXT,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_conference_abstracts_body
    ON mol_raw.conference_abstracts (conference_body);

-- Grant to mol_data_ops if the role exists (non-fatal if it doesn't)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.conference_abstracts TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.conference_abstracts_id_seq TO mol_data_ops;
    END IF;
END
$$;

COMMIT;

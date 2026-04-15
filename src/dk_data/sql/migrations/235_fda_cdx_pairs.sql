-- Migration 235: mol_raw.fda_cdx_pairs
-- FDA Companion Diagnostic (CDx) device-drug pairings
-- Standard mol_raw JSONB pattern for scraped web data.
-- Feature: 006-claims-engine-data-gaps (T035)

BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.fda_cdx_pairs (
    id                      BIGSERIAL PRIMARY KEY,
    request_id              TEXT        NOT NULL UNIQUE,
    api_endpoint            TEXT,
    api_version             TEXT,
    request_params          JSONB,
    response_status         INTEGER,
    response_body           JSONB,
    response_body_hash      TEXT,
    source_id               TEXT        NOT NULL DEFAULT 'fda_cdx_pairs',
    request_timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_bronze     BOOLEAN     NOT NULL DEFAULT FALSE,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS mol_raw_fda_cdx_pairs_processed_idx
    ON mol_raw.fda_cdx_pairs (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;

CREATE INDEX IF NOT EXISTS mol_raw_fda_cdx_pairs_ingested_idx
    ON mol_raw.fda_cdx_pairs (ingested_at);

-- Grant to mol_data_ops if the role exists (non-fatal if it doesn't)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_cdx_pairs TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_cdx_pairs_id_seq TO mol_data_ops;
    END IF;
END
$$;

COMMIT;

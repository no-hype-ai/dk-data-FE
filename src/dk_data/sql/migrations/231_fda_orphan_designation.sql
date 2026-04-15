-- Migration 231: mol_raw.fda_orphan_designation
-- FDA Office of Orphan Products Development (OOPD) designation database
-- Standard mol_raw pattern (request_id, response_body JSONB, etc.)
-- Feature: 006-claims-engine-data-gaps (T018)

BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.fda_orphan_designation (
    id                      BIGSERIAL PRIMARY KEY,
    request_id              TEXT        NOT NULL UNIQUE,
    api_endpoint            TEXT,
    api_version             TEXT,
    request_params          JSONB,
    response_status         INTEGER,
    response_body           JSONB,
    response_body_hash      TEXT,
    source_id               TEXT        NOT NULL DEFAULT 'fda_orphan_designation',
    request_timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_bronze     BOOLEAN     NOT NULL DEFAULT FALSE,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS mol_raw_fda_orphan_designation_processed_idx
    ON mol_raw.fda_orphan_designation (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;

CREATE INDEX IF NOT EXISTS mol_raw_fda_orphan_designation_ingested_idx
    ON mol_raw.fda_orphan_designation (ingested_at);

-- Grant to mol_data_ops if the role exists (non-fatal if it doesn't)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_orphan_designation TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_orphan_designation_id_seq TO mol_data_ops;
    END IF;
END
$$;

COMMIT;

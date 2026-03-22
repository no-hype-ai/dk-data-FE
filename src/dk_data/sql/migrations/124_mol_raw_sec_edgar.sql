-- Migration 124: Create mol_raw.sec_edgar with standard medallion schema
-- SEC EDGAR was using non-standard typed columns; now uses response_body JSONB pattern
-- so SQLMesh mol_bronze.sec_edgar model can process it correctly.

CREATE TABLE IF NOT EXISTS mol_raw.sec_edgar (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100),
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500),
    request_params JSONB,
    response_status INTEGER NOT NULL DEFAULT 200,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash)
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_sec_edgar_timestamp ON mol_raw.sec_edgar (request_timestamp);
CREATE INDEX IF NOT EXISTS idx_mol_raw_sec_edgar_processed ON mol_raw.sec_edgar (processed_to_bronze) WHERE processed_to_bronze = FALSE;

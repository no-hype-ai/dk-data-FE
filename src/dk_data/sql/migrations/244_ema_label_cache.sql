-- Migration 244: EMA SmPC label cache table
-- Lazy-loaded: populated on first query per product, not bulk-ingested.
BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.ema_label_cache (
    id              BIGSERIAL    PRIMARY KEY,
    medicine_name   TEXT         NOT NULL,
    active_substance TEXT,
    smpc_pdf_url    TEXT         NOT NULL,
    extracted_text  JSONB        NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(smpc_pdf_url)
);

CREATE INDEX IF NOT EXISTS idx_ema_label_cache_medicine
    ON mol_raw.ema_label_cache (LOWER(medicine_name));
CREATE INDEX IF NOT EXISTS idx_ema_label_cache_substance
    ON mol_raw.ema_label_cache (LOWER(active_substance));
CREATE INDEX IF NOT EXISTS idx_ema_label_cache_ingested
    ON mol_raw.ema_label_cache (ingested_at DESC);

COMMIT;

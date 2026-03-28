-- Migration 108: Add cpc_codes column to mol_raw.epo_patents
-- EPO OPS exchange-document elements include epo:classification-cpc sections.
-- Previously only IPC codes were extracted; CPC extraction added to fetcher.

ALTER TABLE mol_raw.epo_patents
    ADD COLUMN IF NOT EXISTS cpc_codes TEXT[];

CREATE INDEX IF NOT EXISTS idx_epo_cpc ON mol_raw.epo_patents USING GIN(cpc_codes);

-- Migration 125: EuropePMC Integration
-- Creates mol_raw.europepmc table, registers source in ops.sync_schedules,
-- and grants access to analyst role.
BEGIN;

-- ══════════════════════════════════════════════════════════════════════════════
-- 1. mol_raw.europepmc — raw JSONB storage (same pattern as other mol_raw tables)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.europepmc (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name            TEXT,                    -- search term used (for per-molecule ingest)
    molecule_id          UUID,                    -- mol_silver.molecules FK (when triggered per-molecule)
    request_url          TEXT,
    request_params       JSONB,
    response_status      INTEGER NOT NULL,
    response_body        JSONB,                   -- full EuropePMC search response
    response_body_hash   TEXT,                    -- SHA-256 of response body (matches raw_ingestion.py convention)
    processed_to_bronze  BOOLEAN DEFAULT FALSE,
    request_timestamp    TIMESTAMPTZ DEFAULT NOW(),
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_europepmc_drug_name  ON mol_raw.europepmc(drug_name);
CREATE INDEX IF NOT EXISTS idx_europepmc_molecule    ON mol_raw.europepmc(molecule_id);
CREATE INDEX IF NOT EXISTS idx_europepmc_ts          ON mol_raw.europepmc(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_europepmc_processed   ON mol_raw.europepmc(processed_to_bronze) WHERE processed_to_bronze = FALSE;

-- ══════════════════════════════════════════════════════════════════════════════
-- 2. Register in ops.sync_schedules (validated by ingest route)
-- ══════════════════════════════════════════════════════════════════════════════
INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options)
VALUES (
    'europepmc',
    'weekly',
    '0 4 * * 0',   -- 04:00 UTC Sunday
    'low',
    true,
    '{
        "source_name": "Europe PMC",
        "api_type": "rest",
        "target_table": "mol_raw.europepmc",
        "base_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        "rate_limit_rps": 10,
        "requires_auth": false,
        "supports_per_molecule": true,
        "unique_value": "full_text_open_access_preprints_entity_annotations"
    }'::jsonb
)
ON CONFLICT (source) DO UPDATE
    SET tier            = EXCLUDED.tier,
        cron_expression = EXCLUDED.cron_expression,
        priority        = EXCLUDED.priority,
        enabled         = EXCLUDED.enabled,
        options         = EXCLUDED.options;

-- ══════════════════════════════════════════════════════════════════════════════
-- 3. Grants
-- ══════════════════════════════════════════════════════════════════════════════
GRANT SELECT ON mol_raw.europepmc TO analyst;

COMMIT;

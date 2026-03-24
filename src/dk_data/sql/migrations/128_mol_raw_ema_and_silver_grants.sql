-- Migration 128: Create mol_raw.ema + PostgREST grants for new silver tables
-- mol_raw.ema is the source table for mol_bronze.ema (bronze/ema.sql), which
-- feeds mol_silver.ema_regulatory and mol_silver.regulatory_decisions.
-- This table was referenced in bronze/ema.sql but never created in any migration.
--
-- Also grants SELECT on new silver tables created by SQLMesh so PostgREST
-- can serve them: pubchem, drugbank, cochrane_reviews, ema_regulatory.
--
-- Note: the actual silver tables are created by SQLMesh on first model run.
-- Grants use IF EXISTS pattern to be safe.

BEGIN;

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.ema — EMA authorized medicine responses
-- Standard medallion schema: response_body JSONB, processed_to_bronze flag
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.ema (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name           TEXT,
    molecule_id         UUID,
    request_url         TEXT,
    request_params      JSONB,
    response_status     INTEGER NOT NULL,
    response_body       JSONB,
    response_hash       TEXT,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
-- Only create drug_name index if the column exists (table may have a different schema)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_raw' AND table_name='ema' AND column_name='drug_name') THEN
        CREATE INDEX IF NOT EXISTS idx_ema_raw_drug ON mol_raw.ema(drug_name);
    END IF;
    CREATE INDEX IF NOT EXISTS idx_ema_raw_ts   ON mol_raw.ema(ingested_at);
    CREATE INDEX IF NOT EXISTS idx_ema_raw_flag ON mol_raw.ema(processed_to_bronze) WHERE processed_to_bronze = FALSE;
END $$;

-- Register ema_regulatory in ops.sync_schedules if not already there
INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options)
VALUES (
    'ema_regulatory', 'monthly', '0 4 10 * *', 'normal', true,
    '{"source_name":"EMA Medicines","api_type":"rest","target_table":"mol_raw.ema","supports_per_molecule":true}'::jsonb
)
ON CONFLICT (source) DO UPDATE
    SET tier            = EXCLUDED.tier,
        cron_expression = EXCLUDED.cron_expression,
        enabled         = EXCLUDED.enabled,
        options         = EXCLUDED.options;

-- Grant access to mol_raw.ema
GRANT SELECT ON mol_raw.ema TO analyst;

-- ══════════════════════════════════════════════════════════════════════════════
-- PostgREST grants for new silver tables (created by SQLMesh on first run)
-- Using DO block to skip gracefully if table doesn't exist yet
-- ══════════════════════════════════════════════════════════════════════════════
DO $$
BEGIN
    -- mol_silver.pubchem — PubChem compound data
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'mol_silver' AND table_name = 'pubchem') THEN
        GRANT SELECT ON mol_silver.pubchem TO analyst;
    END IF;

    -- mol_silver.drugbank — DrugBank pharmacological data
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'mol_silver' AND table_name = 'drugbank') THEN
        GRANT SELECT ON mol_silver.drugbank TO analyst;
    END IF;

    -- mol_silver.cochrane_reviews — Cochrane systematic reviews
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'mol_silver' AND table_name = 'cochrane_reviews') THEN
        GRANT SELECT ON mol_silver.cochrane_reviews TO analyst;
    END IF;

    -- mol_silver.ema_regulatory — EMA authorized medicines
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'mol_silver' AND table_name = 'ema_regulatory') THEN
        GRANT SELECT ON mol_silver.ema_regulatory TO analyst;
    END IF;

    -- mol_gold.market_summary — market/financial summary per molecule
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'mol_gold' AND table_name = 'market_summary') THEN
        GRANT SELECT ON mol_gold.market_summary TO analyst;
    END IF;
END;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- Event trigger: auto-grant SELECT to analyst on new mol_silver/mol_gold tables
-- This ensures any future SQLMesh-created tables are immediately PostgREST-accessible
-- without requiring a new migration.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION grant_analyst_on_new_mol_table()
RETURNS event_trigger AS $$
DECLARE
    obj record;
BEGIN
    FOR obj IN SELECT * FROM pg_event_trigger_ddl_commands()
    LOOP
        IF obj.command_tag = 'CREATE TABLE'
           AND (obj.schema_name = 'mol_silver' OR obj.schema_name = 'mol_gold') THEN
            EXECUTE format('GRANT SELECT ON %I.%I TO analyst',
                           obj.schema_name,
                           split_part(obj.object_identity, '.', 2));
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Create event trigger only if it doesn't already exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_event_trigger WHERE evtname = 'auto_grant_mol_tables'
    ) THEN
        CREATE EVENT TRIGGER auto_grant_mol_tables
            ON ddl_command_end
            WHEN TAG IN ('CREATE TABLE')
            EXECUTE FUNCTION grant_analyst_on_new_mol_table();
    END IF;
END;
$$;

COMMIT;

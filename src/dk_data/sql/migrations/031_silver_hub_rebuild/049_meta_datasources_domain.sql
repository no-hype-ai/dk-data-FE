-- Migration 049: Add domain_schema column to meta.data_sources
-- Part of: 001-silver-medallion-rebuild (T107a prerequisite)
-- meta.data_sources is created by migration 083 which runs after this subdirectory.
-- Guard: skip if the table does not exist yet.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'meta' AND table_name = 'data_sources'
    ) THEN
        RAISE NOTICE 'meta.data_sources does not exist yet — skipping';
        RETURN;
    END IF;

    ALTER TABLE meta.data_sources
        ADD COLUMN IF NOT EXISTS domain_schema TEXT DEFAULT 'mol_silver';

    COMMENT ON COLUMN meta.data_sources.domain_schema IS
        'The target silver schema for this source (e.g. mol_silver, ip_silver, hcs_silver, ind_silver, hcp_silver).';

    UPDATE meta.data_sources SET domain_schema = 'ip_silver'
    WHERE source_name IN ('uspto_patents', 'uspto_ci', 'uspto_trademarks', 'epo_ops', 'euipo_trademarks', 'euipo_designs');

    UPDATE meta.data_sources SET domain_schema = 'hcs_silver'
    WHERE source_name LIKE 'cms_%';

    UPDATE meta.data_sources SET domain_schema = 'ind_silver'
    WHERE source_name IN ('who_icd', 'who_inn', 'who_gho');
END $$;

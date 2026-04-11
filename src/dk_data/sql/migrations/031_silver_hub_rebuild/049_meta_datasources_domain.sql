-- Migration 049: Add domain_schema column to meta.data_sources
-- Part of: 001-silver-medallion-rebuild (T107a prerequisite)
-- Adds domain_schema TEXT column so each source knows which silver schema it maps to.

BEGIN;

ALTER TABLE meta.data_sources
    ADD COLUMN IF NOT EXISTS domain_schema TEXT DEFAULT 'mol_silver';

COMMENT ON COLUMN meta.data_sources.domain_schema IS
    'The target silver schema for this source (e.g. mol_silver, ip_silver, hcs_silver, ind_silver, hcp_silver). '
    'Used by the transform pipeline to route rows to the correct domain.';

-- Update IP sources to ip_silver
UPDATE meta.data_sources SET domain_schema = 'ip_silver'
WHERE source_name IN (
    'uspto_patents',
    'uspto_ci',
    'uspto_trademarks',
    'epo_ops',
    'euipo_trademarks',
    'euipo_designs'
);

-- Update HCS sources to hcs_silver
UPDATE meta.data_sources SET domain_schema = 'hcs_silver'
WHERE source_name LIKE 'cms_%';

-- Update IND sources to ind_silver
UPDATE meta.data_sources SET domain_schema = 'ind_silver'
WHERE source_name IN ('who_icd', 'who_inn', 'who_gho');

COMMIT;

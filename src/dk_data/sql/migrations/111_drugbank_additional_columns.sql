-- Migration 111: DrugBank additional columns
-- Adds columns to mol_raw.drugbank that are now extracted by DrugBankFetcher:
--   state, groups, food_interactions, patents, international_brands,
--   monoisotopic_mass, unii
-- route_of_elimination, clearance, volume_of_distribution were already added
-- in migration 110 but the fetcher didn't yet extract them — now it does.

-- Drug physical state
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS state                   TEXT;

-- Drug regulatory groups (approved, investigational, withdrawn, etc.)
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS groups                  JSONB;

-- Food interactions
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS food_interactions       JSONB;

-- Patents from DrugBank XML <patents>
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS patents                 JSONB;

-- International brand names
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS international_brands    JSONB;

-- Monoisotopic mass from experimental-properties
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS monoisotopic_mass       TEXT;

-- FDA UNII code from external-identifiers
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS unii                    TEXT;

-- Index on unii for cross-reference joins
CREATE INDEX IF NOT EXISTS idx_mol_raw_drugbank_unii
    ON mol_raw.drugbank (unii)
    WHERE unii IS NOT NULL;

-- Migration 110: DrugBank extended columns
-- Adds structural, pharmacological, and classification columns to mol_raw.drugbank
-- that the DrugBankFetcher now extracts from the XML (calculated-properties,
-- pharmacology fields, ATC codes, pathways, interactions, synonyms).
-- Required to close the data pipeline gap where the fetcher extracted these
-- fields but the table had no columns to store them.

-- Structural identifiers (from <calculated-properties>)
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS smiles              TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS inchi               TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS inchi_key           TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS molecular_formula   TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS molecular_weight    TEXT;

-- Drug classification
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS drug_type           TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS atc_codes           JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS classification      JSONB;

-- Pharmacokinetics / pharmacodynamics
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS mechanism_of_action TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS absorption          TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS protein_binding     TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS metabolism          TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS half_life           TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS route_of_elimination TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS clearance           TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS volume_of_distribution TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS toxicity            TEXT;

-- Relational data
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS carriers            JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS transporters        JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS pathways            JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS drug_interactions   JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS synonyms            JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS external_identifiers JSONB;

-- Raw property blobs (for completeness / future use)
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS calculated_properties  JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS experimental_properties JSONB;

-- Index on inchi_key for identifier-mapping joins
CREATE INDEX IF NOT EXISTS idx_mol_raw_drugbank_inchi_key
    ON mol_raw.drugbank (inchi_key)
    WHERE inchi_key IS NOT NULL;

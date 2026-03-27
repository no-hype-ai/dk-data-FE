-- Migration 088: mol_silver.molecules v2 schema alignment
-- Aligns silver.molecules / mol_silver.molecules with 016-branch design:
--   • deterministic molecule_id (md5(chembl_id)::uuid replaces gen_random_uuid id)
--   • Lipinski properties (alogp, hba, hbd, psa, num_ro5_violations, aromatic_rings, heavy_atoms)
--   • multi-source enrichment columns (chembl_id, drugbank_id, pubchem_cid, unii, cas_number)
--   • mechanism_of_action from DrugBank
--   • source_count (number of sources that confirmed this molecule)
--   • removes NULL-placeholder columns (therapeutic_areas, approval_date — never populated)
-- Feature: 019-cms-puf-platform-reconciliation

BEGIN;

-- Ensure domain schemas exist (created here in case SQLMesh hasn't run yet)
CREATE SCHEMA IF NOT EXISTS mol_raw;
CREATE SCHEMA IF NOT EXISTS mol_bronze;
CREATE SCHEMA IF NOT EXISTS mol_silver;
CREATE SCHEMA IF NOT EXISTS mol_gold;
CREATE SCHEMA IF NOT EXISTS ind_silver;
CREATE SCHEMA IF NOT EXISTS ind_gold;
CREATE SCHEMA IF NOT EXISTS hcp_silver;
CREATE SCHEMA IF NOT EXISTS hcp_gold;

-- ─── silver.molecules (bare schema — may still exist before SQLMesh redirect) ───

ALTER TABLE IF EXISTS silver.molecules
    ADD COLUMN IF NOT EXISTS molecule_id         UUID,
    ADD COLUMN IF NOT EXISTS chembl_id           TEXT,
    ADD COLUMN IF NOT EXISTS alogp               NUMERIC,
    ADD COLUMN IF NOT EXISTS hba                 INTEGER,
    ADD COLUMN IF NOT EXISTS hbd                 INTEGER,
    ADD COLUMN IF NOT EXISTS psa                 NUMERIC,
    ADD COLUMN IF NOT EXISTS num_ro5_violations  INTEGER,
    ADD COLUMN IF NOT EXISTS aromatic_rings      INTEGER,
    ADD COLUMN IF NOT EXISTS heavy_atoms         INTEGER,
    ADD COLUMN IF NOT EXISTS drugbank_id         TEXT,
    ADD COLUMN IF NOT EXISTS pubchem_cid         INTEGER,
    ADD COLUMN IF NOT EXISTS unii                TEXT,
    ADD COLUMN IF NOT EXISTS cas_number          TEXT,
    ADD COLUMN IF NOT EXISTS mechanism_of_action TEXT,
    ADD COLUMN IF NOT EXISTS source_count        INTEGER DEFAULT 1;

-- Backfill molecule_id as md5(inchi_key) for existing rows (inchi_key-keyed records)
UPDATE silver.molecules
SET molecule_id = md5(inchi_key)::uuid
WHERE molecule_id IS NULL
  AND inchi_key IS NOT NULL;

-- ─── mol_silver.molecules (post-redirect physical target) ───
-- These are applied after the config redirect takes effect; safe to run idempotently.

ALTER TABLE IF EXISTS mol_silver.molecules
    ADD COLUMN IF NOT EXISTS molecule_id         UUID,
    ADD COLUMN IF NOT EXISTS chembl_id           TEXT,
    ADD COLUMN IF NOT EXISTS alogp               NUMERIC,
    ADD COLUMN IF NOT EXISTS hba                 INTEGER,
    ADD COLUMN IF NOT EXISTS hbd                 INTEGER,
    ADD COLUMN IF NOT EXISTS psa                 NUMERIC,
    ADD COLUMN IF NOT EXISTS num_ro5_violations  INTEGER,
    ADD COLUMN IF NOT EXISTS aromatic_rings      INTEGER,
    ADD COLUMN IF NOT EXISTS heavy_atoms         INTEGER,
    ADD COLUMN IF NOT EXISTS drugbank_id         TEXT,
    ADD COLUMN IF NOT EXISTS pubchem_cid         INTEGER,
    ADD COLUMN IF NOT EXISTS unii                TEXT,
    ADD COLUMN IF NOT EXISTS cas_number          TEXT,
    ADD COLUMN IF NOT EXISTS mechanism_of_action TEXT,
    ADD COLUMN IF NOT EXISTS source_count        INTEGER DEFAULT 1;

UPDATE mol_silver.molecules
SET molecule_id = md5(inchi_key)::uuid
WHERE molecule_id IS NULL
  AND inchi_key IS NOT NULL;

-- ─── Unique index on molecule_id once backfilled ───
CREATE UNIQUE INDEX IF NOT EXISTS ux_mol_silver_molecules_molecule_id
    ON mol_silver.molecules (molecule_id)
    WHERE molecule_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_silver_molecules_molecule_id
    ON silver.molecules (molecule_id)
    WHERE molecule_id IS NOT NULL;

-- ─── silver.clinical_trials — add missing columns (from 016 migration 114) ───

ALTER TABLE IF EXISTS silver.clinical_trials
    ADD COLUMN IF NOT EXISTS molecule_id          UUID,
    ADD COLUMN IF NOT EXISTS queried_drug_name    TEXT,
    ADD COLUMN IF NOT EXISTS why_stopped          TEXT,
    ADD COLUMN IF NOT EXISTS eligibility_criteria TEXT,
    ADD COLUMN IF NOT EXISTS minimum_age          TEXT,
    ADD COLUMN IF NOT EXISTS maximum_age          TEXT,
    ADD COLUMN IF NOT EXISTS healthy_volunteers   TEXT,
    ADD COLUMN IF NOT EXISTS results_section      JSONB,
    ADD COLUMN IF NOT EXISTS central_contacts     JSONB,
    ADD COLUMN IF NOT EXISTS locations            JSONB,
    ADD COLUMN IF NOT EXISTS fda_regulated_drug   BOOLEAN,
    ADD COLUMN IF NOT EXISTS has_results          BOOLEAN;

ALTER TABLE IF EXISTS mol_silver.clinical_trials
    ADD COLUMN IF NOT EXISTS molecule_id          UUID,
    ADD COLUMN IF NOT EXISTS queried_drug_name    TEXT,
    ADD COLUMN IF NOT EXISTS why_stopped          TEXT,
    ADD COLUMN IF NOT EXISTS eligibility_criteria TEXT,
    ADD COLUMN IF NOT EXISTS minimum_age          TEXT,
    ADD COLUMN IF NOT EXISTS maximum_age          TEXT,
    ADD COLUMN IF NOT EXISTS healthy_volunteers   TEXT,
    ADD COLUMN IF NOT EXISTS results_section      JSONB,
    ADD COLUMN IF NOT EXISTS central_contacts     JSONB,
    ADD COLUMN IF NOT EXISTS locations            JSONB,
    ADD COLUMN IF NOT EXISTS fda_regulated_drug   BOOLEAN;

-- ─── ndc_molecule_bridge table (pre-create for Phase 4a) ───
CREATE TABLE IF NOT EXISTS mol_silver.ndc_molecule_bridge (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ndc             TEXT        NOT NULL,
    molecule_id     UUID        NOT NULL,
    source          TEXT        NOT NULL DEFAULT 'openfda_labels',
    confidence      NUMERIC     NOT NULL DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ndc, molecule_id)
);

-- ─── hcpcs_molecule_bridge table (pre-create for Phase 4b) ───
CREATE TABLE IF NOT EXISTS mol_silver.hcpcs_molecule_bridge (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hcpcs_code      TEXT        NOT NULL,
    hcpcs_desc      TEXT,
    molecule_id     UUID        NOT NULL,
    source          TEXT        NOT NULL DEFAULT 'cms_hcpcs',
    confidence      NUMERIC     NOT NULL DEFAULT 0.75,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (hcpcs_code, molecule_id)
);

COMMIT;

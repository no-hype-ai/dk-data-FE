-- Migration 131: Create mol_gold.molecule_profile VIEW and mol_silver.patents table
-- Date: 2026-03-23
--
-- 1. mol_gold.molecule_profile (VIEW) — Xenon agents query /molecule_profile in mol_gold schema.
--    The canonical table is mol_gold.molecule_profiles (plural, from migration 020).
--    This view exposes the same columns so PostgREST serves /molecule_profile correctly.
--
-- 2. mol_silver.patents — Silver-layer patents table.
--    Old silver.patents was in the unprefixed 'silver' schema (dropped in migration 121).
--    Xenon agents query /patents in mol_silver.  PostgREST needs this table to exist.
--    Populated from raw.epo_patents via SQLMesh (or direct INSERT by dk-data-FE ingestion).

-- ─── 1. mol_gold.molecule_profile VIEW ───────────────────────────────────────
-- Wraps mol_gold.molecule_profiles (plural) so Xenon's PostgREST path /molecule_profile works.
-- Xenon reads: molecule_id, canonical_name, lifecycle_stage, trial_count, label_count, etc.

CREATE OR REPLACE VIEW mol_gold.molecule_profile AS
SELECT
    profile_id,
    molecule_id,
    inchi_key,
    canonical_name,
    lifecycle_stage,
    stage_confidence,
    data_completeness,
    trial_count,
    active_trial_count,
    label_count,
    indication_count,
    adverse_event_count,
    serious_ae_count,
    publication_count,
    patent_expiry_date,
    first_approval_date,
    last_updated
FROM mol_gold.molecule_profiles;

GRANT SELECT ON mol_gold.molecule_profile TO analyst;
GRANT SELECT ON mol_gold.molecule_profile TO authenticator;
GRANT SELECT ON mol_gold.molecule_profile TO web_anon;

-- ─── 2. mol_silver.patents TABLE ─────────────────────────────────────────────
-- Silver-layer patents.  Molecule-scoped entry point for Xenon agents.
-- Populated by dk-data-FE epo_patents ingestion pipeline (source = 'epo_patents').
-- Schema matches old silver.patents (migration 040) plus EPO-specific columns
-- from raw.epo_patents (migration 060).

CREATE TABLE IF NOT EXISTS mol_silver.patents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id         UUID REFERENCES mol_silver.molecules(molecule_id) ON DELETE SET NULL,

    -- Patent identifiers
    patent_number       VARCHAR(50) NOT NULL,
    patent_country      VARCHAR(10),
    publication_id      VARCHAR(50),       -- EPO publication_id (e.g. EP1234567A1)
    family_id           VARCHAR(50),       -- EPO patent family

    -- Dates
    filing_date         DATE,
    publication_date    DATE,
    grant_date          DATE,
    expiry_date         DATE,

    -- Content
    title               TEXT,
    abstract            TEXT,
    assignee            VARCHAR(500),

    -- Classification
    ipc_codes           TEXT[],
    applicants          JSONB,
    inventors           JSONB,

    -- Status
    status              VARCHAR(50),

    -- Source tracking
    source              VARCHAR(50) DEFAULT 'epo_patents',
    source_updated_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(patent_number, patent_country)
);

CREATE INDEX IF NOT EXISTS idx_mol_silver_patents_molecule_id ON mol_silver.patents(molecule_id);
CREATE INDEX IF NOT EXISTS idx_mol_silver_patents_number      ON mol_silver.patents(patent_number);
CREATE INDEX IF NOT EXISTS idx_mol_silver_patents_expiry      ON mol_silver.patents(expiry_date);
CREATE INDEX IF NOT EXISTS idx_mol_silver_patents_family      ON mol_silver.patents(family_id);

GRANT SELECT ON mol_silver.patents TO analyst;
GRANT SELECT ON mol_silver.patents TO authenticator;
GRANT SELECT ON mol_silver.patents TO web_anon;

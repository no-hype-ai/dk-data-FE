-- Migration 153: Create mol_agents.publication_evidence_staging
-- The mol_silver.publication_evidence SQLMesh model reads from this table.
-- Migration 086 created the table in mol_silver, but the model references mol_agents.
-- This creates the canonical table in mol_agents where agents write staging records.

CREATE TABLE IF NOT EXISTS mol_agents.publication_evidence_staging (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_hash            TEXT NOT NULL UNIQUE,
    molecule_id             UUID,
    trial_nct_id            TEXT,
    pmid                    TEXT NOT NULL,
    doi                     TEXT,
    endpoint_name           TEXT NOT NULL,
    endpoint_type           TEXT,
    hazard_ratio            NUMERIC(10,4),
    p_value                 NUMERIC(10,6),
    response_rate           NUMERIC(10,4),
    median_survival_months  NUMERIC(10,2),
    sample_size             INTEGER,
    confidence_score        NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review            BOOLEAN NOT NULL DEFAULT FALSE,
    evidence_date           DATE,
    source_model            TEXT NOT NULL DEFAULT 'publication_evidence_extractor',
    staged_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promoted_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pub_evidence_staging_molecule
    ON mol_agents.publication_evidence_staging (molecule_id);
CREATE INDEX IF NOT EXISTS idx_pub_evidence_staging_promoted
    ON mol_agents.publication_evidence_staging (promoted_at)
    WHERE promoted_at IS NULL;

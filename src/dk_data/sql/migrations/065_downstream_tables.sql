-- Migration 065: Downstream API view backing tables
-- Feature: 012-platform-hardening (US2)

-- Table: mol_gold.company_pipeline
CREATE TABLE IF NOT EXISTS mol_gold.company_pipeline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name VARCHAR(255) NOT NULL,
    molecule_name VARCHAR(255) NOT NULL,
    molecule_id UUID REFERENCES mol_gold.molecule_profiles(molecule_id),
    indication VARCHAR(500),
    phase VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'Active',
    mechanism_of_action VARCHAR(500),
    source VARCHAR(100),
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_name, molecule_name, indication)
);

CREATE INDEX IF NOT EXISTS idx_company_pipeline_company ON mol_gold.company_pipeline(company_name);
CREATE INDEX IF NOT EXISTS idx_company_pipeline_phase ON mol_gold.company_pipeline(phase);

-- Table: mol_gold.trial_publication_features
CREATE TABLE IF NOT EXISTS mol_gold.trial_publication_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nct_id VARCHAR(20) NOT NULL,
    publication_doi VARCHAR(255),
    publication_pmid VARCHAR(20),
    overlap_score NUMERIC(5,4) CHECK (overlap_score >= 0 AND overlap_score <= 1),
    feature_type VARCHAR(50) NOT NULL,
    trial_title TEXT,
    publication_title TEXT,
    source VARCHAR(100),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nct_id, publication_doi, feature_type)
);

CREATE INDEX IF NOT EXISTS idx_trial_pub_nct ON mol_gold.trial_publication_features(nct_id);
CREATE INDEX IF NOT EXISTS idx_trial_pub_doi ON mol_gold.trial_publication_features(publication_doi);

-- Table: mol_silver.targets
CREATE TABLE IF NOT EXISTS mol_silver.targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_name VARCHAR(255) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    uniprot_accession VARCHAR(20),
    gene_symbol VARCHAR(50),
    organism VARCHAR(100) DEFAULT 'Homo sapiens',
    molecule_id UUID REFERENCES mol_gold.molecule_profiles(molecule_id),
    molecule_name VARCHAR(255),
    action_type VARCHAR(50),
    binding_affinity NUMERIC(12,4),
    source VARCHAR(100),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(target_name, molecule_name, source)
);

CREATE INDEX IF NOT EXISTS idx_targets_uniprot ON mol_silver.targets(uniprot_accession);
CREATE INDEX IF NOT EXISTS idx_targets_gene ON mol_silver.targets(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_targets_molecule ON mol_silver.targets(molecule_id);

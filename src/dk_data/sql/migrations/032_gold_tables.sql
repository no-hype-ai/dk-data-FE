-- Migration: 032_gold_tables.sql
-- Description: Create Gold layer tables for pre-aggregated, decision-ready data
-- Date: 2026-01-23
-- Part of: 012-dk-data-platform

-- ==========================================
-- Molecule Profile (Pre-aggregated)
-- ==========================================

CREATE TABLE IF NOT EXISTS gold_molecule_profile (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID UNIQUE NOT NULL REFERENCES silver_molecules(molecule_id) ON DELETE CASCADE,

    -- Identity
    preferred_name VARCHAR(500),
    molecule_type VARCHAR(30),
    inchi_key VARCHAR(27),

    -- Current Lifecycle Stage
    lifecycle_stage VARCHAR(50),
    lifecycle_stage_confidence DECIMAL,
    lifecycle_last_detected TIMESTAMPTZ,

    -- Key Identifiers (denormalized for fast access)
    drugbank_id VARCHAR(20),
    chembl_id VARCHAR(20),
    pubchem_cid VARCHAR(20),
    rxnorm_cui VARCHAR(20),
    unii VARCHAR(20),

    -- Indications (aggregated)
    approved_indications JSONB, -- [{name, icd10, approval_date, region}]
    pipeline_indications JSONB, -- [{name, phase, trial_count}]

    -- Safety Summary
    boxed_warning_count INTEGER DEFAULT 0,
    serious_ae_count INTEGER DEFAULT 0,
    ae_summary JSONB, -- Top adverse events with counts

    -- Competitive Position
    therapeutic_area VARCHAR(100),
    mechanism_of_action VARCHAR(500),
    competitor_count INTEGER DEFAULT 0,

    -- Patent Status
    earliest_patent_expiry DATE,
    patent_count INTEGER DEFAULT 0,
    exclusivity_expiry DATE,

    -- Data Completeness
    data_completeness_score DECIMAL, -- 0-1
    data_sources JSONB, -- {source: record_count}
    last_data_update TIMESTAMPTZ,

    -- Aggregation Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    aggregation_run_id UUID
);

CREATE INDEX idx_gold_profile_name ON gold_molecule_profile(preferred_name);
CREATE INDEX idx_gold_profile_stage ON gold_molecule_profile(lifecycle_stage);
CREATE INDEX idx_gold_profile_drugbank ON gold_molecule_profile(drugbank_id);
CREATE INDEX idx_gold_profile_therapeutic ON gold_molecule_profile(therapeutic_area);

-- ==========================================
-- Lifecycle Stages
-- ==========================================

CREATE TABLE IF NOT EXISTS gold_lifecycle_stages (
    stage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL REFERENCES silver_molecules(molecule_id) ON DELETE CASCADE,

    -- Indication-specific lifecycle
    indication VARCHAR(500),
    indication_mesh VARCHAR(50),

    -- Stage Details
    stage VARCHAR(50) NOT NULL,
    stage_confidence DECIMAL NOT NULL,
    detected_at TIMESTAMPTZ DEFAULT NOW(),

    -- Evidence Count
    evidence_count INTEGER DEFAULT 0,
    primary_evidence_type VARCHAR(50),

    -- Previous Stage (for tracking progression)
    previous_stage VARCHAR(50),
    stage_changed_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, indication)
);

CREATE INDEX idx_gold_lifecycle_molecule ON gold_lifecycle_stages(molecule_id);
CREATE INDEX idx_gold_lifecycle_stage ON gold_lifecycle_stages(stage);
CREATE INDEX idx_gold_lifecycle_indication ON gold_lifecycle_stages(indication);

-- Stage values reference:
-- 'discovery', 'preclinical', 'phase_1', 'phase_2', 'phase_3', 'submitted', 'approved', 'marketed', 'withdrawn', 'discontinued'

-- ==========================================
-- Lifecycle Evidence Links
-- ==========================================

CREATE TABLE IF NOT EXISTS gold_lifecycle_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stage_id UUID NOT NULL REFERENCES gold_lifecycle_stages(stage_id) ON DELETE CASCADE,

    -- Evidence Details
    evidence_type VARCHAR(50) NOT NULL,
    evidence_source VARCHAR(50) NOT NULL,
    evidence_id_external VARCHAR(100), -- NCT ID, NDA number, etc.

    -- Contribution to Stage
    supports_stage VARCHAR(50),
    evidence_strength VARCHAR(20), -- strong, moderate, weak

    -- Source Link
    source_url TEXT,
    source_title TEXT,
    source_date DATE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_gold_evidence_stage ON gold_lifecycle_evidence(stage_id);
CREATE INDEX idx_gold_evidence_type ON gold_lifecycle_evidence(evidence_type);

-- Evidence types:
-- 'clinical_trial', 'fda_approval', 'ema_approval', 'patent', 'publication', 'press_release', 'label', 'regulatory_action'

-- ==========================================
-- Competitive Landscape (by Indication)
-- ==========================================

CREATE TABLE IF NOT EXISTS gold_competitive_landscape (
    landscape_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Indication
    indication VARCHAR(500) NOT NULL,
    indication_mesh VARCHAR(50),
    therapeutic_area VARCHAR(100),

    -- Landscape Summary
    total_molecules INTEGER DEFAULT 0,
    approved_count INTEGER DEFAULT 0,
    phase_3_count INTEGER DEFAULT 0,
    phase_2_count INTEGER DEFAULT 0,
    phase_1_count INTEGER DEFAULT 0,
    preclinical_count INTEGER DEFAULT 0,

    -- Top Players
    market_leaders JSONB, -- [{molecule_id, name, market_share_estimate}]
    recent_approvals JSONB, -- [{molecule_id, name, approval_date}]
    late_stage_pipeline JSONB, -- [{molecule_id, name, phase, sponsor}]

    -- Mechanism of Action Distribution
    moa_distribution JSONB, -- {moa: count}

    -- Patent Landscape
    upcoming_patent_expiries JSONB, -- [{molecule_id, name, expiry_date}]

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    snapshot_date DATE DEFAULT CURRENT_DATE,

    UNIQUE(indication, snapshot_date)
);

CREATE INDEX idx_gold_landscape_indication ON gold_competitive_landscape(indication);
CREATE INDEX idx_gold_landscape_therapeutic ON gold_competitive_landscape(therapeutic_area);
CREATE INDEX idx_gold_landscape_date ON gold_competitive_landscape(snapshot_date);

-- ==========================================
-- Safety Signals (Aggregated)
-- ==========================================

CREATE TABLE IF NOT EXISTS gold_safety_signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL REFERENCES silver_molecules(molecule_id) ON DELETE CASCADE,

    -- Adverse Event
    reaction_name VARCHAR(500) NOT NULL,
    reaction_meddra_pt VARCHAR(100),

    -- Signal Metrics
    case_count INTEGER DEFAULT 0,
    serious_count INTEGER DEFAULT 0,
    fatal_count INTEGER DEFAULT 0,

    -- Disproportionality (vs background)
    pro_score DECIMAL, -- Proportional Reporting Ratio
    ror_score DECIMAL, -- Reporting Odds Ratio
    is_signal BOOLEAN DEFAULT FALSE,

    -- Time Trend
    first_reported DATE,
    last_reported DATE,
    trend_direction VARCHAR(20), -- increasing, stable, decreasing

    -- Comparison
    vs_class_average DECIMAL, -- relative to therapeutic class

    -- Metadata
    calculated_at TIMESTAMPTZ DEFAULT NOW(),
    faers_quarter VARCHAR(10) -- e.g., '2026Q1'
);

CREATE INDEX idx_gold_safety_molecule ON gold_safety_signals(molecule_id);
CREATE INDEX idx_gold_safety_signal ON gold_safety_signals(is_signal) WHERE is_signal = TRUE;
CREATE INDEX idx_gold_safety_reaction ON gold_safety_signals(reaction_meddra_pt);

-- ==========================================
-- Aggregation Run Log
-- ==========================================

CREATE TABLE IF NOT EXISTS gold_aggregation_runs (
    id SERIAL PRIMARY KEY,
    aggregation_type VARCHAR(50) NOT NULL, -- profile, lifecycle, landscape, safety

    -- Run details
    run_id UUID DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'partial')),

    -- Metrics
    records_processed INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,

    -- Errors
    error_details JSONB,

    -- Trigger
    triggered_by VARCHAR(50), -- scheduled, manual, silver_update
    silver_run_id UUID
);

CREATE INDEX idx_gold_agg_type ON gold_aggregation_runs(aggregation_type);
CREATE INDEX idx_gold_agg_status ON gold_aggregation_runs(status);

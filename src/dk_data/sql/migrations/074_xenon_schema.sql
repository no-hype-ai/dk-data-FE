-- Migration: 074_xenon_schema
-- Feature: 015-assessment-dashboard-integration
-- Purpose: Create xenon application schema with assessment_generated and publication_evidence tables
-- Date: 2026-02-25

BEGIN;

-- =============================================================================
-- STEP 1: CREATE XENON SCHEMA
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS xenon;

-- =============================================================================
-- STEP 2: xenon.assessment_generated — AI-generated assessment content
-- Outside medallion pipeline (Constraint 5). Written by xenon NestJS agents.
-- =============================================================================

CREATE TABLE IF NOT EXISTS xenon.assessment_generated (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL,
    section_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    generation_source VARCHAR(100),
    generation_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- FR-005: Deduplication on (molecule_id, section_type, version)
    CONSTRAINT uq_assessment_molecule_section_version
        UNIQUE (molecule_id, section_type, version),

    -- Validate section_type against allowed values
    CONSTRAINT chk_assessment_section_type CHECK (
        section_type IN (
            'executive_summary',
            'key_metrics',
            'financial_analysis',
            'hcp_segmentation',
            'patient_journey',
            'market_opportunity',
            'dosing_administration',
            'risk_assessment',
            'strategic_recommendations',
            'investment_thesis'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_assessment_molecule_section
    ON xenon.assessment_generated (molecule_id, section_type);

CREATE INDEX IF NOT EXISTS idx_assessment_created_at
    ON xenon.assessment_generated (created_at DESC);

-- =============================================================================
-- STEP 3: xenon.publication_evidence — LLM-extracted clinical evidence
-- Outside medallion pipeline (Constraint 5). Feeds mol_gold.trial_outcomes UNION.
-- =============================================================================

CREATE TABLE IF NOT EXISTS xenon.publication_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL,
    trial_nct_id VARCHAR(20),
    endpoint_name VARCHAR(200) NOT NULL,
    endpoint_type VARCHAR(50),
    hazard_ratio NUMERIC(8,4),
    p_value NUMERIC(10,8),
    response_rate NUMERIC(5,2),
    median_survival_months NUMERIC(6,1),
    sample_size INTEGER,
    confidence_score NUMERIC(3,2) NOT NULL,
    evidence_source VARCHAR(20) NOT NULL DEFAULT 'publication',
    doi VARCHAR(100),
    pmid VARCHAR(20),
    extraction_metadata JSONB,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- FR-009: Deduplication on content_hash
    CONSTRAINT uq_pub_evidence_content_hash UNIQUE (content_hash),

    -- Confidence score must be between 0.0 and 1.0
    CONSTRAINT chk_pub_evidence_confidence CHECK (
        confidence_score >= 0.0 AND confidence_score <= 1.0
    ),

    -- Validate endpoint_type
    CONSTRAINT chk_pub_evidence_endpoint_type CHECK (
        endpoint_type IS NULL OR endpoint_type IN ('primary', 'secondary', 'exploratory')
    )
);

CREATE INDEX IF NOT EXISTS idx_pub_evidence_molecule
    ON xenon.publication_evidence (molecule_id);

-- Partial index for trial_outcomes UNION view (confidence >= 0.40)
CREATE INDEX IF NOT EXISTS idx_pub_evidence_confidence
    ON xenon.publication_evidence (confidence_score)
    WHERE confidence_score >= 0.40;

CREATE INDEX IF NOT EXISTS idx_pub_evidence_trial
    ON xenon.publication_evidence (trial_nct_id)
    WHERE trial_nct_id IS NOT NULL;

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 074_xenon_schema complete.';
    RAISE NOTICE 'Created xenon schema with assessment_generated and publication_evidence tables.';
END $$;

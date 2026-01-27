-- Migration: 033_onboarding_tables.sql
-- Description: Create Application layer tables for molecule onboarding and user tracking
-- Date: 2026-01-23
-- Part of: 012-dk-data-platform

-- ==========================================
-- User-Tracked Molecules
-- NOTE: One row per molecule+indication combination
-- ==========================================

CREATE TABLE IF NOT EXISTS user_tracked_molecules (
    tracking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Indication-specific tracking (one row per indication)
    indication VARCHAR(500),
    indication_mesh_term VARCHAR(50),

    -- Tracking config
    tracking_name VARCHAR(500),
    notes TEXT,

    -- Indication-specific lifecycle stage (may differ from Gold profile)
    tracked_stage VARCHAR(50),
    tracked_stage_confidence DECIMAL,

    -- Onboarding status
    onboarding_completed BOOLEAN DEFAULT FALSE,
    onboarding_step INTEGER DEFAULT 1 CHECK (onboarding_step >= 1 AND onboarding_step <= 10),
    onboarding_started_at TIMESTAMPTZ,
    onboarding_completed_at TIMESTAMPTZ,

    -- Wizard step data (auto-saved)
    wizard_data JSONB DEFAULT '{}',

    -- Validation
    stage_validated BOOLEAN DEFAULT FALSE,
    stage_validated_at TIMESTAMPTZ,
    stage_validated_by UUID,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Allow same user to track same molecule for different indications
    UNIQUE(user_id, molecule_id, indication)
);

CREATE INDEX idx_tracked_user ON user_tracked_molecules(user_id);
CREATE INDEX idx_tracked_molecule ON user_tracked_molecules(molecule_id);
CREATE INDEX idx_tracked_onboarding ON user_tracked_molecules(onboarding_completed) WHERE onboarding_completed = FALSE;
CREATE INDEX idx_tracked_validation ON user_tracked_molecules(stage_validated) WHERE stage_validated = FALSE;

-- ==========================================
-- User Annotations (Manual Evidence)
-- ==========================================

CREATE TABLE IF NOT EXISTS user_annotations (
    annotation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    tracking_id UUID REFERENCES user_tracked_molecules(tracking_id) ON DELETE CASCADE,

    -- Annotation
    annotation_type VARCHAR(50) NOT NULL
        CHECK (annotation_type IN ('evidence', 'note', 'correction', 'flag', 'question')),
    title VARCHAR(500),
    content TEXT,
    source_url TEXT,
    source_date DATE,

    -- For evidence annotations
    evidence_type VARCHAR(100),
    supports_stage VARCHAR(50),

    -- Visibility
    is_private BOOLEAN DEFAULT TRUE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_annotations_user ON user_annotations(user_id);
CREATE INDEX idx_annotations_molecule ON user_annotations(molecule_id);
CREATE INDEX idx_annotations_tracking ON user_annotations(tracking_id);
CREATE INDEX idx_annotations_type ON user_annotations(annotation_type);

-- ==========================================
-- Alert Configurations
-- ==========================================

CREATE TABLE IF NOT EXISTS user_alert_configs (
    alert_config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    tracking_id UUID REFERENCES user_tracked_molecules(tracking_id) ON DELETE CASCADE,

    -- Alert types
    alert_on_stage_change BOOLEAN DEFAULT TRUE,
    alert_on_trial_update BOOLEAN DEFAULT TRUE,
    alert_on_safety_signal BOOLEAN DEFAULT TRUE,
    alert_on_regulatory_action BOOLEAN DEFAULT TRUE,
    alert_on_patent_event BOOLEAN DEFAULT FALSE,
    alert_on_publication BOOLEAN DEFAULT FALSE,
    alert_on_competitor_news BOOLEAN DEFAULT FALSE,

    -- Delivery
    delivery_method VARCHAR(20) DEFAULT 'in_app'
        CHECK (delivery_method IN ('email', 'webhook', 'in_app')),
    delivery_frequency VARCHAR(20) DEFAULT 'immediate'
        CHECK (delivery_frequency IN ('immediate', 'daily_digest', 'weekly_digest')),
    webhook_url TEXT,
    email_address VARCHAR(255),

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alert_config_user ON user_alert_configs(user_id);
CREATE INDEX idx_alert_config_molecule ON user_alert_configs(molecule_id);
CREATE INDEX idx_alert_config_active ON user_alert_configs(is_active) WHERE is_active = TRUE;

-- ==========================================
-- Alert History
-- ==========================================

CREATE TABLE IF NOT EXISTS alert_history (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    alert_config_id UUID REFERENCES user_alert_configs(alert_config_id) ON DELETE SET NULL,

    -- Alert details
    alert_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    data JSONB,

    -- Severity
    severity VARCHAR(20) DEFAULT 'info'
        CHECK (severity IN ('info', 'warning', 'critical')),

    -- Delivery
    delivered_at TIMESTAMPTZ,
    delivery_method VARCHAR(20),
    delivery_status VARCHAR(20) DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'delivered', 'failed', 'skipped')),
    delivery_error TEXT,

    -- User interaction
    read_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    action_taken VARCHAR(50),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alert_history_user ON alert_history(user_id);
CREATE INDEX idx_alert_history_molecule ON alert_history(molecule_id);
CREATE INDEX idx_alert_history_unread ON alert_history(read_at) WHERE read_at IS NULL;
CREATE INDEX idx_alert_history_pending ON alert_history(delivery_status) WHERE delivery_status = 'pending';

-- ==========================================
-- Onboarding Audit Log
-- ==========================================

CREATE TABLE IF NOT EXISTS onboarding_audit_log (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Context
    user_id UUID NOT NULL,
    molecule_id UUID,
    tracking_id UUID,

    -- Action
    action_type VARCHAR(50) NOT NULL,
    action_details JSONB,

    -- Before/after state
    previous_state JSONB,
    new_state JSONB,

    -- Metadata
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON onboarding_audit_log(user_id);
CREATE INDEX idx_audit_molecule ON onboarding_audit_log(molecule_id);
CREATE INDEX idx_audit_tracking ON onboarding_audit_log(tracking_id);
CREATE INDEX idx_audit_action ON onboarding_audit_log(action_type);
CREATE INDEX idx_audit_created ON onboarding_audit_log(created_at);

-- Action types:
-- 'onboard_start', 'onboard_step_complete', 'onboard_complete', 'onboard_resume',
-- 'stage_validate', 'stage_override', 'evidence_add', 'evidence_remove',
-- 'alert_config_create', 'alert_config_update', 'note_add', 'molecule_untrack'

-- ==========================================
-- Stage Validation Records
-- ==========================================

CREATE TABLE IF NOT EXISTS stage_validations (
    validation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    tracking_id UUID NOT NULL REFERENCES user_tracked_molecules(tracking_id) ON DELETE CASCADE,
    molecule_id UUID NOT NULL REFERENCES silver_molecules(molecule_id),
    user_id UUID NOT NULL,

    -- Validation Details
    validated_stage VARCHAR(50) NOT NULL,
    validation_result VARCHAR(20) NOT NULL
        CHECK (validation_result IN ('passed', 'failed', 'override')),

    -- Evidence Summary
    required_evidence_count INTEGER DEFAULT 0,
    present_evidence_count INTEGER DEFAULT 0,
    missing_evidence JSONB,
    evidence_details JSONB,

    -- Override (if applicable)
    override_reason TEXT,
    override_approved_by UUID,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_stage_val_tracking ON stage_validations(tracking_id);
CREATE INDEX idx_stage_val_molecule ON stage_validations(molecule_id);
CREATE INDEX idx_stage_val_result ON stage_validations(validation_result);

-- ==========================================
-- Bulk Onboarding Jobs
-- ==========================================

CREATE TABLE IF NOT EXISTS bulk_onboarding_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User
    user_id UUID NOT NULL,

    -- Job Details
    file_name VARCHAR(500),
    file_size_bytes INTEGER,
    total_rows INTEGER,

    -- Progress
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    processed_rows INTEGER DEFAULT 0,
    successful_rows INTEGER DEFAULT 0,
    failed_rows INTEGER DEFAULT 0,

    -- Results
    success_tracking_ids JSONB, -- Array of created tracking_ids
    error_details JSONB, -- [{row, error, data}]

    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bulk_jobs_user ON bulk_onboarding_jobs(user_id);
CREATE INDEX idx_bulk_jobs_status ON bulk_onboarding_jobs(status);

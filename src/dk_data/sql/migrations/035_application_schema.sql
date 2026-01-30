-- Migration: 035_application_schema.sql
-- Description: Create application schema and additional onboarding tables
-- Date: 2026-01-24
-- Part of: 012-dk-data-platform

-- ==========================================
-- Application Schema
-- ==========================================

CREATE SCHEMA IF NOT EXISTS application;

-- ==========================================
-- Onboarding Request Queue
-- For async molecule onboarding workflow
-- ==========================================

CREATE TABLE IF NOT EXISTS application.onboarding_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID,
    user_id UUID NOT NULL,

    -- Identifiers to resolve
    identifiers JSONB NOT NULL, -- [{identifier_type, identifier_value}]

    -- Priority (0-10, higher = more urgent)
    priority INTEGER DEFAULT 0 CHECK (priority >= 0 AND priority <= 10),

    -- Status
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'resolving', 'ingesting', 'enriching',
                          'completed', 'failed', 'needs_review')),

    -- Resolution result
    molecule_id UUID,
    inchi_key VARCHAR(27),
    resolution_confidence DECIMAL,

    -- Processing
    requested_sources JSONB,
    skip_enrichment BOOLEAN DEFAULT FALSE,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Errors
    error_message TEXT,
    error_details JSONB,

    -- Notes
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_onboard_queue_status ON application.onboarding_queue(status);
CREATE INDEX idx_onboard_queue_user ON application.onboarding_queue(user_id);
CREATE INDEX idx_onboard_queue_batch ON application.onboarding_queue(batch_id);
CREATE INDEX idx_onboard_queue_pending ON application.onboarding_queue(priority DESC, created_at)
    WHERE status = 'pending';

-- ==========================================
-- Onboarding Audit Log (application schema)
-- ==========================================

CREATE TABLE IF NOT EXISTS application.onboarding_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    user_id UUID NOT NULL,

    -- Action
    action VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,

    -- Details
    details JSONB,
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_app_audit_request ON application.onboarding_audit_log(request_id);
CREATE INDEX idx_app_audit_user ON application.onboarding_audit_log(user_id);
CREATE INDEX idx_app_audit_action ON application.onboarding_audit_log(action);

-- ==========================================
-- User Molecule Updates Feed
-- Tracks changes to tracked molecules
-- ==========================================

CREATE TABLE IF NOT EXISTS application.molecule_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL,

    -- Update type
    update_type VARCHAR(50) NOT NULL
        CHECK (update_type IN ('trial_new', 'trial_status_change', 'trial_results',
                               'safety_signal', 'label_update', 'label_boxed_warning',
                               'regulatory_approval', 'regulatory_rejection',
                               'publication_new', 'patent_event', 'competitor_news',
                               'stage_change', 'data_refresh')),

    -- Update details
    title VARCHAR(500) NOT NULL,
    description TEXT,
    data JSONB,

    -- Source reference
    source_type VARCHAR(50),
    source_id VARCHAR(100),
    source_url TEXT,

    -- Impact
    severity VARCHAR(20) DEFAULT 'info'
        CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),

    -- Timestamp
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_mol_updates_molecule ON application.molecule_updates(molecule_id);
CREATE INDEX idx_mol_updates_type ON application.molecule_updates(update_type);
CREATE INDEX idx_mol_updates_detected ON application.molecule_updates(detected_at DESC);
CREATE INDEX idx_mol_updates_severity ON application.molecule_updates(severity)
    WHERE severity IN ('high', 'critical');

-- ==========================================
-- User Update Read Status
-- ==========================================

CREATE TABLE IF NOT EXISTS application.user_update_reads (
    user_id UUID NOT NULL,
    update_id UUID NOT NULL REFERENCES application.molecule_updates(id) ON DELETE CASCADE,
    read_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, update_id)
);

CREATE INDEX idx_update_reads_user ON application.user_update_reads(user_id);

-- ==========================================
-- Tracked Molecule Tags
-- Normalized tags for tracked molecules
-- ==========================================

CREATE TABLE IF NOT EXISTS application.tracking_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    tag_name VARCHAR(100) NOT NULL,
    tag_color VARCHAR(7),  -- Hex color
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, tag_name)
);

CREATE TABLE IF NOT EXISTS application.tracking_tag_assignments (
    tracking_id UUID NOT NULL,
    tag_id UUID NOT NULL REFERENCES application.tracking_tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tracking_id, tag_id)
);

CREATE INDEX idx_tag_assignments_tracking ON application.tracking_tag_assignments(tracking_id);

-- ==========================================
-- Saved Searches
-- ==========================================

CREATE TABLE IF NOT EXISTS application.saved_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,

    -- Search details
    name VARCHAR(200) NOT NULL,
    description TEXT,
    search_type VARCHAR(50) NOT NULL
        CHECK (search_type IN ('molecule', 'trial', 'company', 'competitive')),

    -- Search parameters
    query_params JSONB NOT NULL,

    -- Notifications
    notify_on_new_results BOOLEAN DEFAULT FALSE,
    last_result_count INTEGER DEFAULT 0,
    last_run_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_saved_searches_user ON application.saved_searches(user_id);
CREATE INDEX idx_saved_searches_notify ON application.saved_searches(notify_on_new_results)
    WHERE notify_on_new_results = TRUE;

-- ==========================================
-- Export Jobs
-- ==========================================

CREATE TABLE IF NOT EXISTS application.export_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,

    -- Export details
    export_type VARCHAR(50) NOT NULL
        CHECK (export_type IN ('molecules', 'trials', 'safety', 'competitive', 'portfolio')),
    format VARCHAR(20) NOT NULL
        CHECK (format IN ('csv', 'xlsx', 'json', 'pdf')),

    -- Filters applied
    filters JSONB,

    -- Status
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'expired')),

    -- Result
    file_path TEXT,
    file_size_bytes INTEGER,
    row_count INTEGER,

    -- Error handling
    error_message TEXT,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_export_jobs_user ON application.export_jobs(user_id);
CREATE INDEX idx_export_jobs_status ON application.export_jobs(status);
CREATE INDEX idx_export_jobs_pending ON application.export_jobs(created_at) WHERE status = 'pending';

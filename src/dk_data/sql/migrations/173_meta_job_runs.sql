-- Migration 031/044: meta.job_runs table for job-trigger run tracking
-- Feature: 001-silver-medallion-rebuild / T191

CREATE TABLE IF NOT EXISTS meta.job_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    job_name      TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'killed')),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at      TIMESTAMPTZ,
    pod_name      TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_runs_job_name ON meta.job_runs (job_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_status   ON meta.job_runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_started  ON meta.job_runs (started_at DESC);

COMMENT ON TABLE meta.job_runs IS
    'Records each fetcher/transform invocation from the job-trigger service. '
    'Status transitions: running → completed | failed | killed. '
    'Feature: 001-silver-medallion-rebuild T191.';

-- Migration 068: Schema migrations tracking table
-- Feature: 013-observability-governance (US4 - Migration Runner)
--
-- Creates meta.schema_migrations to track which SQL migrations
-- have been applied and their checksums for drift detection.

BEGIN;

CREATE TABLE IF NOT EXISTS meta.schema_migrations (
    id              SERIAL PRIMARY KEY,
    version         VARCHAR(10)  NOT NULL UNIQUE,
    filename        VARCHAR(255) NOT NULL,
    checksum        VARCHAR(64)  NOT NULL,  -- SHA-256 hex digest
    applied_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    applied_by      VARCHAR(100) DEFAULT 'migration-runner',
    execution_time_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
    ON meta.schema_migrations (applied_at DESC);

COMMIT;

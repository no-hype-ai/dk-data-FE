-- API View Contracts: Observability & Platform Governance
-- Feature: 013-observability-governance
-- Date: 2026-02-15
--
-- These contracts define the expected columns and types for new API views.
-- Used by contract tests to validate schema compliance.

-- ============================================================================
-- VIEW: api.audit_log
-- Purpose: Queryable audit trail for compliance review (US3)
-- Access: api_user only
-- ============================================================================
-- Expected columns:
--   id              BIGINT       NOT NULL  (row identifier)
--   request_id      UUID         NOT NULL  (correlation ID)
--   timestamp       TIMESTAMPTZ  NOT NULL  (event time)
--   source          VARCHAR(20)  NOT NULL  (job-trigger, postgrest, cronjob)
--   method          VARCHAR(10)            (HTTP method, nullable for cronjob)
--   path            TEXT                   (endpoint path, nullable for cronjob)
--   user_role       VARCHAR(50)            (JWT role claim)
--   user_sub        VARCHAR(255)           (JWT subject claim)
--   status_code     SMALLINT               (HTTP response status)
--   response_time_ms INTEGER               (duration in ms)
--   action          VARCHAR(50)            (audit action type)
--   category        VARCHAR(20)            (audit category)
--   details         JSONB                  (additional context)
--   created_at      TIMESTAMPTZ  NOT NULL  (row creation time)

-- Access control:
GRANT SELECT ON api.audit_log TO api_user;
-- REVOKE from all other roles (append-only, admin-read)

-- ============================================================================
-- VIEW: api.migration_status
-- Purpose: Operational visibility of applied database migrations (US4)
-- Access: api_user only
-- ============================================================================
-- Expected columns:
--   version           VARCHAR(10)   NOT NULL  (migration number prefix)
--   filename          VARCHAR(255)  NOT NULL  (full migration filename)
--   applied_at        TIMESTAMPTZ   NOT NULL  (when applied)
--   applied_by        VARCHAR(100)            (who/what applied it)
--   execution_time_ms INTEGER                 (execution duration)

-- Access control:
GRANT SELECT ON api.migration_status TO api_user;

-- ============================================================================
-- VIEW: api.data_classification
-- Purpose: Table-level data sensitivity classification (US5)
-- Access: api_user only
-- ============================================================================
-- Expected columns:
--   schema_name      VARCHAR(50)   NOT NULL  (PostgreSQL schema)
--   table_name       VARCHAR(100)  NOT NULL  (table name)
--   classification   VARCHAR(20)   NOT NULL  (public, internal, pii, confidential)
--   pii_fields       TEXT[]                  (column names containing PII)
--   retention_days   INTEGER                 (retention period, NULL = perpetual)
--   retention_policy VARCHAR(50)             (purge strategy)
--   notes            TEXT                    (context/justification)

-- Access control:
GRANT SELECT ON api.data_classification TO api_user;

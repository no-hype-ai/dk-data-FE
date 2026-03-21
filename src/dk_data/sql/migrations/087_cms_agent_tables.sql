-- Migration 087: CMS Agent Infrastructure Tables (016-cms-puf-datasource-integration)
--
-- Agent execution log is APPEND-ONLY per dk-canon audit integrity rules.
-- No UPDATE or DELETE grants are issued on the execution log.

BEGIN;

-- ─── Agent Execution Log (APPEND-ONLY) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS meta.ops_agent_execution_log (
    id                    UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name            TEXT            NOT NULL,
    agent_version         TEXT            NOT NULL,
    started_at            TIMESTAMPTZ     NOT NULL,
    completed_at          TIMESTAMPTZ,
    status                TEXT            NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    records_input         INTEGER,
    records_enriched      INTEGER,
    records_quarantined   INTEGER,
    error_message         TEXT,
    model_used            TEXT            NOT NULL,
    cost_usd              NUMERIC(10,4),
    created_at            TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_exec_log_name
    ON meta.ops_agent_execution_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_exec_log_status
    ON meta.ops_agent_execution_log(status);

-- ─── Agent Quarantine ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meta.ops_agent_quarantine (
    id                    UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name            TEXT            NOT NULL,
    execution_id          UUID            REFERENCES meta.ops_agent_execution_log(id),
    record_data           JSONB           NOT NULL,
    reason                TEXT            NOT NULL,
    confidence_score      NUMERIC,
    status                TEXT            NOT NULL DEFAULT 'PENDING'
                                          CHECK (status IN ('PENDING', 'RESOLVED', 'REJECTED')),
    resolved_by           TEXT,
    resolved_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_quarantine_status
    ON meta.ops_agent_quarantine(status);
CREATE INDEX IF NOT EXISTS idx_agent_quarantine_agent
    ON meta.ops_agent_quarantine(agent_name);

-- ─── Permissions ──────────────────────────────────────────────────────────────

-- Execution log: append-only (INSERT + SELECT only, NO UPDATE OR DELETE)
GRANT INSERT, SELECT ON meta.ops_agent_execution_log TO api_user;
GRANT SELECT ON meta.ops_agent_execution_log TO analyst;

-- Quarantine: reviewable (INSERT + SELECT + UPDATE for resolution workflow)
GRANT INSERT, SELECT, UPDATE ON meta.ops_agent_quarantine TO api_user;
GRANT SELECT ON meta.ops_agent_quarantine TO analyst;

COMMIT;

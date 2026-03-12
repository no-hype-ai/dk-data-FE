-- Migration 094: Molecule Stage History
-- Audit table for lifecycle stage transitions (012-dk-data-platform)
-- Used by lifecycle_detection.py get_stage_transitions()

CREATE TABLE IF NOT EXISTS silver.molecule_stage_history (
    id              BIGSERIAL PRIMARY KEY,
    molecule_id     UUID NOT NULL,
    previous_stage  TEXT,
    new_stage       TEXT NOT NULL,
    confidence      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    evidence_summary TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_molecule_stage_history_molecule_id
    ON silver.molecule_stage_history (molecule_id);

CREATE INDEX IF NOT EXISTS idx_molecule_stage_history_detected_at
    ON silver.molecule_stage_history (detected_at);

COMMENT ON TABLE silver.molecule_stage_history
    IS 'Audit trail of molecule lifecycle stage transitions detected by LifecycleDetectionService';

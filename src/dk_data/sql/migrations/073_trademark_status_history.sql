-- Migration: 073_trademark_status_history
-- Feature: 014-uspto-euipo-model-datasource
-- Purpose: Track trademark status changes over time for both USPTO and EUIPO

CREATE TABLE IF NOT EXISTS ops.trademark_status_history (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    trademark_identifier VARCHAR(30) NOT NULL,
    source VARCHAR(20) NOT NULL CHECK (source IN ('uspto_trademarks', 'euipo_trademarks')),
    old_status VARCHAR(100),
    new_status VARCHAR(100) NOT NULL,
    change_detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_tm_history_identifier
    ON ops.trademark_status_history(trademark_identifier, source);
CREATE INDEX IF NOT EXISTS idx_tm_history_detected
    ON ops.trademark_status_history(change_detected_at DESC);

DO $$
BEGIN
    RAISE NOTICE 'Migration 073_trademark_status_history complete.';
END
$$;

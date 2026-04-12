-- Migration: 003_meta_linkage_conflicts.sql
-- Feature: 001-silver-medallion-rebuild
-- FR-026a: meta.linkage_conflicts — crosswalk deduplication conflict audit.
--
-- When a crosswalk re-run would assign a different hub_id to an already-known
-- (source, identifier) pair, the conflict is logged here instead of silently
-- overwriting the existing row.  This prevents downstream gold-layer joins from
-- silently breaking across bootstrap re-runs.
--
-- Operators can query:
--   SELECT source, COUNT(*) FROM meta.linkage_conflicts GROUP BY source;
-- to check for data-quality drift between source versions.

BEGIN;

CREATE TABLE IF NOT EXISTS meta.linkage_conflicts (
    conflict_id      bigserial    PRIMARY KEY,
    detected_at      timestamptz  DEFAULT NOW(),
    source           text         NOT NULL,
    identifier       text         NOT NULL,
    existing_hub_id  bigint       NOT NULL,
    new_hub_id       bigint       NOT NULL,
    procedure_name   text         NOT NULL
);

CREATE INDEX IF NOT EXISTS meta_linkage_conflicts_detected_at_idx
    ON meta.linkage_conflicts (detected_at);
CREATE INDEX IF NOT EXISTS meta_linkage_conflicts_procedure_name_idx
    ON meta.linkage_conflicts (procedure_name);

COMMENT ON TABLE meta.linkage_conflicts IS
    'FR-026a: audit log for crosswalk rows where a re-run would change hub_id. '
    'A non-empty table after bootstrap indicates source data changed between runs.';

COMMENT ON COLUMN meta.linkage_conflicts.source IS
    'Source system name, e.g. ''chembl'', ''drugbank'', ''nppes''.';
COMMENT ON COLUMN meta.linkage_conflicts.identifier IS
    'The source-system identifier that conflicted.';
COMMENT ON COLUMN meta.linkage_conflicts.existing_hub_id IS
    'hub_id already in the crosswalk table.';
COMMENT ON COLUMN meta.linkage_conflicts.new_hub_id IS
    'hub_id the re-run would have assigned — kept here for investigation.';

COMMIT;

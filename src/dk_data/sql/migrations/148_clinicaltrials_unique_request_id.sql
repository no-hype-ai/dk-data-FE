-- Migration 148: Restore full unique index on mol_raw.clinicaltrials(request_id)
--
-- Context:
--   Migration 123 created uidx_mol_raw_clinicaltrials_request_id as a full unique index.
--   It was dropped at some point (root cause unknown). The clinicaltrials fetcher uses
--   ON CONFLICT (request_id) which requires a full (non-partial) unique index — a partial
--   index (WHERE request_id IS NOT NULL) does NOT satisfy this constraint.
--
--   This migration is idempotent: it drops any existing partial variant and recreates
--   the full unique index, and also ensures openfda_labels has the same fix.

DROP INDEX IF EXISTS uidx_mol_raw_clinicaltrials_request_id;
CREATE UNIQUE INDEX uidx_mol_raw_clinicaltrials_request_id
    ON mol_raw.clinicaltrials(request_id);

DROP INDEX IF EXISTS uidx_mol_raw_openfda_labels_request_id;
CREATE UNIQUE INDEX uidx_mol_raw_openfda_labels_request_id
    ON mol_raw.openfda_labels(request_id);

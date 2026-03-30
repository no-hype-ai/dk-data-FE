-- Migration 123: Add unique indexes on mol_raw.clinicaltrials and mol_raw.openfda_labels
-- Enables ON CONFLICT (request_id) upserts in the clinicaltrials and openfda_labels loaders.
-- The existing idx_raw_ct_request_id is a plain index; this adds a UNIQUE index alongside it.

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_clinicaltrials_request_id
    ON mol_raw.clinicaltrials(request_id);

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_openfda_labels_request_id
    ON mol_raw.openfda_labels(request_id);

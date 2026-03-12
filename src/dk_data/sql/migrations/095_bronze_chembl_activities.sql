-- Migration 095: Bronze ChEMBL Activities
-- Stores ChEMBL bioactivity data in the Bronze layer (012-dk-data-platform)
-- Used by bronze_ingestion.py _insert_bronze_chembl_activity()

CREATE TABLE IF NOT EXISTS bronze.chembl_activities (
    id                      BIGSERIAL PRIMARY KEY,
    raw_id                  UUID REFERENCES raw.chembl(id),
    activity_id             BIGINT,
    molecule_chembl_id      TEXT NOT NULL,
    target_chembl_id        TEXT,
    target_name             TEXT,
    target_organism         TEXT,
    activity_type           TEXT,          -- IC50, Ki, EC50, Kd, etc.
    activity_value          DOUBLE PRECISION,
    activity_units          TEXT,
    assay_chembl_id         TEXT,
    assay_type              TEXT,
    assay_description       TEXT,
    pchembl_value           DOUBLE PRECISION,
    data_validity_comment   TEXT,
    pubmed_id               TEXT,
    processed_to_silver     BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_chembl_activity UNIQUE (molecule_chembl_id, activity_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_chembl_activities_molecule
    ON bronze.chembl_activities (molecule_chembl_id);

CREATE INDEX IF NOT EXISTS idx_bronze_chembl_activities_target
    ON bronze.chembl_activities (target_chembl_id);

CREATE INDEX IF NOT EXISTS idx_bronze_chembl_activities_unprocessed
    ON bronze.chembl_activities (processed_to_silver) WHERE processed_to_silver = FALSE;

COMMENT ON TABLE bronze.chembl_activities
    IS 'ChEMBL bioactivity data — Bronze layer, extracted from raw.chembl JSON';

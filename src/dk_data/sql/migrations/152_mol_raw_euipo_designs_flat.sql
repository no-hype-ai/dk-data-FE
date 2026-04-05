-- Migration 152: Recreate mol_raw.euipo_designs as flat typed table
-- Feature: 026-fetcher-checkpoint-resume
--
-- Migration 096 created mol_raw.euipo_designs as a JSONB envelope table.
-- Migration 137 tried to create the flat-column version but used IF NOT EXISTS,
-- making it a no-op. The euipo_designs.py loader inserts flat columns, so the
-- table was empty (loader failed with "column not found"). This migration drops
-- the old schema and creates the correct flat table that the loader expects.
--
-- The table is empty in production (all inserts failed), so data loss is zero.

DROP TABLE IF EXISTS mol_raw.euipo_designs;

CREATE TABLE mol_raw.euipo_designs (
    id                  BIGSERIAL PRIMARY KEY,
    application_number  TEXT NOT NULL,
    design_title        TEXT,
    applicant_name      TEXT,
    applicant_country   TEXT,
    representative_name TEXT,
    designer_name       TEXT,
    status              TEXT,
    filing_date         DATE,
    registration_date   DATE,
    expiry_date         DATE,
    publication_date    DATE,
    locarno_classes     JSONB,
    product_indication  TEXT,
    image_url           TEXT,
    number_of_designs   INTEGER,
    _source_file        TEXT,
    _source_hash        TEXT,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (application_number)
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_euipo_designs_ts
    ON mol_raw.euipo_designs (_loaded_at);

GRANT SELECT ON mol_raw.euipo_designs TO analyst;

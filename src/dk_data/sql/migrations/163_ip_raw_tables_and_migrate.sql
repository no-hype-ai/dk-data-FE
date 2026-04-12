-- Migration 163: Create ip_raw.* tables and migrate data from mol_raw.*
--
-- Background: the IP fetcher loaders (src/dk_data/ingestion/sources/uspto_*.py,
-- epo_ops.py, euipo_*.py) all INSERT INTO ip_raw.<table>, but the ip_raw tables
-- were never created. The mol_raw.* shadow tables (created in migration 137)
-- were the only landing place, but the fetchers don't write to them. The
-- ip_bronze SQLMesh models in turn read from mol_raw.* — so the entire IP
-- pipeline has been writing into a void.
--
-- This migration:
--   1. Creates the ip_raw.* tables with the same schemas as the mol_raw shadows
--   2. Copies any rows that did make it into mol_raw.* (e.g. through manual
--      backfill or schema-mismatched runs) into ip_raw.*
--   3. Updates ip_bronze SQLMesh models in a follow-up commit to read from
--      ip_raw instead of mol_raw (handled outside this migration since SQLMesh
--      models are versioned files, not DDL)
--   4. Leaves the mol_raw.* IP tables in place for now; a follow-up migration
--      will drop them once the ip_bronze models have been re-deployed.

BEGIN;

-- Ensure ip_raw schema exists (normally created by 031_silver_hub_rebuild/050_create_ip_schemas.sql
-- but the CI migration runner only scans top-level *.sql files, not subdirectories).
CREATE SCHEMA IF NOT EXISTS ip_raw;

-- ============================================================================
-- ip_raw.uspto_patents
-- ============================================================================
CREATE TABLE IF NOT EXISTS ip_raw.uspto_patents (
    id             BIGSERIAL PRIMARY KEY,
    patent_number  TEXT NOT NULL,
    title          TEXT,
    abstract       TEXT,
    inventors      JSONB,
    assignees      JSONB,
    filing_date    DATE,
    grant_date     DATE,
    cpc_codes      JSONB,
    claims_count   INTEGER,
    patent_type    TEXT,
    _source_file   TEXT,
    _source_hash   TEXT,
    _loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (patent_number)
);
CREATE INDEX IF NOT EXISTS idx_ip_raw_uspto_patents_grant
    ON ip_raw.uspto_patents (grant_date);
CREATE INDEX IF NOT EXISTS idx_ip_raw_uspto_patents_loaded_brin
    ON ip_raw.uspto_patents USING BRIN (_loaded_at) WITH (pages_per_range = 128);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='uspto_patents') THEN
        INSERT INTO ip_raw.uspto_patents (
    patent_number, title, abstract, inventors, assignees,
    filing_date, grant_date, cpc_codes, claims_count, patent_type,
    _source_file, _source_hash, _loaded_at
)
SELECT patent_number, title, abstract, inventors, assignees,
       filing_date, grant_date, cpc_codes, claims_count, patent_type,
       _source_file, _source_hash, _loaded_at
FROM mol_raw.uspto_patents
ON CONFLICT (patent_number) DO NOTHING;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ip_raw data copy skipped (%%): %%', SQLSTATE, SQLERRM;
END $$;

-- ============================================================================
-- ip_raw.uspto_ci
-- ============================================================================
CREATE TABLE IF NOT EXISTS ip_raw.uspto_ci (
    id            BIGSERIAL PRIMARY KEY,
    patent_id     TEXT NOT NULL,
    title         TEXT,
    abstract      TEXT,
    inventors     JSONB,
    assignees     JSONB,
    filing_date   DATE,
    grant_date    DATE,
    cpc_codes     JSONB,
    claims_count  INTEGER,
    _source_file  TEXT,
    _source_hash  TEXT,
    _loaded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (patent_id)
);
CREATE INDEX IF NOT EXISTS idx_ip_raw_uspto_ci_grant
    ON ip_raw.uspto_ci (grant_date);
CREATE INDEX IF NOT EXISTS idx_ip_raw_uspto_ci_loaded_brin
    ON ip_raw.uspto_ci USING BRIN (_loaded_at) WITH (pages_per_range = 128);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='uspto_ci') THEN
        INSERT INTO ip_raw.uspto_ci (
    patent_id, title, abstract, inventors, assignees,
    filing_date, grant_date, cpc_codes, claims_count,
    _source_file, _source_hash, _loaded_at
)
SELECT patent_id, title, abstract, inventors, assignees,
       filing_date, grant_date, cpc_codes, claims_count,
       _source_file, _source_hash, _loaded_at
FROM mol_raw.uspto_ci
ON CONFLICT (patent_id) DO NOTHING;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ip_raw data copy skipped (%%): %%', SQLSTATE, SQLERRM;
END $$;

-- ============================================================================
-- ip_raw.uspto_trademarks
-- ============================================================================
CREATE TABLE IF NOT EXISTS ip_raw.uspto_trademarks (
    id                   BIGSERIAL PRIMARY KEY,
    serial_number        TEXT NOT NULL,
    mark_element         TEXT,
    mark_type            TEXT,
    status               TEXT,
    status_code          TEXT,
    status_date          DATE,
    filing_date          DATE,
    registration_number  TEXT,
    registration_date    DATE,
    nice_classes         JSONB,
    us_classes           JSONB,
    owner_name           TEXT,
    owner_entity_type    TEXT,
    goods_and_services   TEXT,
    description_of_mark  TEXT,
    _source_file         TEXT,
    _source_hash         TEXT,
    _loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (serial_number)
);
CREATE INDEX IF NOT EXISTS idx_ip_raw_uspto_trademarks_loaded_brin
    ON ip_raw.uspto_trademarks USING BRIN (_loaded_at) WITH (pages_per_range = 128);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='uspto_trademarks') THEN
        INSERT INTO ip_raw.uspto_trademarks (
    serial_number, mark_element, mark_type, status, status_code, status_date,
    filing_date, registration_number, registration_date, nice_classes, us_classes,
    owner_name, owner_entity_type, goods_and_services, description_of_mark,
    _source_file, _source_hash, _loaded_at
)
SELECT serial_number, mark_element, mark_type, status, status_code, status_date,
       filing_date, registration_number, registration_date, nice_classes, us_classes,
       owner_name, owner_entity_type, goods_and_services, description_of_mark,
       _source_file, _source_hash, _loaded_at
FROM mol_raw.uspto_trademarks
ON CONFLICT (serial_number) DO NOTHING;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ip_raw data copy skipped (%%): %%', SQLSTATE, SQLERRM;
END $$;

-- ============================================================================
-- ip_raw.epo_patents
-- ============================================================================
CREATE TABLE IF NOT EXISTS ip_raw.epo_patents (
    id               BIGSERIAL PRIMARY KEY,
    publication_id   TEXT NOT NULL,
    title            TEXT,
    abstract         TEXT,
    applicants       JSONB,
    inventors        JSONB,
    filing_date      DATE,
    publication_date DATE,
    ipc_codes        JSONB,
    family_id        TEXT,
    _source_file     TEXT,
    _source_hash     TEXT,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (publication_id)
);
CREATE INDEX IF NOT EXISTS idx_ip_raw_epo_family ON ip_raw.epo_patents (family_id);
CREATE INDEX IF NOT EXISTS idx_ip_raw_epo_loaded_brin
    ON ip_raw.epo_patents USING BRIN (_loaded_at) WITH (pages_per_range = 128);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='epo_patents') THEN
        INSERT INTO ip_raw.epo_patents (
    publication_id, title, abstract, applicants, inventors,
    filing_date, publication_date, ipc_codes, family_id,
    _source_file, _source_hash, _loaded_at
)
SELECT publication_id, title, abstract, applicants, inventors,
       filing_date, publication_date, ipc_codes, family_id,
       _source_file, _source_hash, _loaded_at
FROM mol_raw.epo_patents
ON CONFLICT (publication_id) DO NOTHING;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ip_raw data copy skipped (%%): %%', SQLSTATE, SQLERRM;
END $$;

-- ============================================================================
-- ip_raw.euipo_trademarks
-- ============================================================================
CREATE TABLE IF NOT EXISTS ip_raw.euipo_trademarks (
    id                 BIGSERIAL PRIMARY KEY,
    application_number TEXT NOT NULL,
    mark_name          TEXT,
    mark_kind          TEXT,
    mark_feature       TEXT,
    mark_basis         TEXT,
    applicant_name     TEXT,
    applicant_country  TEXT,
    representative_name TEXT,
    status             TEXT,
    filing_date        DATE,
    registration_date  DATE,
    expiry_date        DATE,
    nice_classes       JSONB,
    goods_and_services TEXT,
    image_url          TEXT,
    _source_file       TEXT,
    _source_hash       TEXT,
    _loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (application_number)
);
CREATE INDEX IF NOT EXISTS idx_ip_raw_euipo_trademarks_loaded_brin
    ON ip_raw.euipo_trademarks USING BRIN (_loaded_at) WITH (pages_per_range = 128);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='euipo_trademarks') THEN
        INSERT INTO ip_raw.euipo_trademarks (
    application_number, mark_name, mark_kind, mark_feature, mark_basis,
    applicant_name, applicant_country, representative_name, status,
    filing_date, registration_date, expiry_date, nice_classes,
    goods_and_services, image_url, _source_file, _source_hash, _loaded_at
)
SELECT application_number, mark_name, mark_kind, mark_feature, mark_basis,
       applicant_name, applicant_country, representative_name, status,
       filing_date, registration_date, expiry_date, nice_classes,
       goods_and_services, image_url, _source_file, _source_hash, _loaded_at
FROM mol_raw.euipo_trademarks
ON CONFLICT (application_number) DO NOTHING;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ip_raw data copy skipped (%%): %%', SQLSTATE, SQLERRM;
END $$;

-- ============================================================================
-- ip_raw.euipo_designs (matches the flat schema from migration 152)
-- ============================================================================
CREATE TABLE IF NOT EXISTS ip_raw.euipo_designs (
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
CREATE INDEX IF NOT EXISTS idx_ip_raw_euipo_designs_loaded_brin
    ON ip_raw.euipo_designs USING BRIN (_loaded_at) WITH (pages_per_range = 128);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='euipo_designs') THEN
        INSERT INTO ip_raw.euipo_designs (
    application_number, design_title, applicant_name, applicant_country,
    representative_name, designer_name, status, filing_date, registration_date,
    expiry_date, publication_date, locarno_classes, product_indication,
    image_url, number_of_designs, _source_file, _source_hash, _loaded_at
)
SELECT application_number, design_title, applicant_name, applicant_country,
       representative_name, designer_name, status, filing_date, registration_date,
       expiry_date, publication_date, locarno_classes, product_indication,
       image_url, number_of_designs, _source_file, _source_hash, _loaded_at
FROM mol_raw.euipo_designs
ON CONFLICT (application_number) DO NOTHING;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ip_raw data copy skipped (%%): %%', SQLSTATE, SQLERRM;
END $$;

-- ============================================================================
-- ip_raw.trademark_status_history
-- ============================================================================
CREATE TABLE IF NOT EXISTS ip_raw.trademark_status_history (
    id                   BIGSERIAL PRIMARY KEY,
    trademark_identifier TEXT NOT NULL,
    source               TEXT NOT NULL,
    old_status           TEXT,
    new_status           TEXT,
    changed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ip_raw_tm_status_hist
    ON ip_raw.trademark_status_history (trademark_identifier, source);
CREATE INDEX IF NOT EXISTS idx_ip_raw_tm_status_hist_changed_brin
    ON ip_raw.trademark_status_history USING BRIN (changed_at) WITH (pages_per_range = 128);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='trademark_status_history') THEN
        INSERT INTO ip_raw.trademark_status_history (
    trademark_identifier, source, old_status, new_status, changed_at
)
SELECT trademark_identifier, source, old_status, new_status, changed_at
FROM mol_raw.trademark_status_history
ON CONFLICT DO NOTHING;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ip_raw data copy skipped (%%): %%', SQLSTATE, SQLERRM;
END $$;

-- Grants follow migration 050_create_ip_schemas.sql (mol_data_ops gets DML on ip_raw)
-- Already covered there via GRANT ALL ON ALL TABLES IN SCHEMA + ALTER DEFAULT PRIVILEGES.

COMMIT;

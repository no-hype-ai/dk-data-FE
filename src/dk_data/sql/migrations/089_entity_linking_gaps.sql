-- Migration 089: Entity Linking Gaps — Part D Prescriber + Open Payments Drug Columns
-- Feature: 020-entity-linking-gaps
-- Date: 2026-03-27
--
-- Closes four known gaps from ENTITY_LINKING_STRATEGY.md:
--   Gap 1: hcs_raw.cms_part_d_prescriber (NPI-level Part D prescribing, new source)
--   Gap 4: ALTER hcs_raw.cms_open_payments to add drug name + NDC columns (1-5 slots)
--
-- Gaps 2 and 3 are pure SQLMesh model changes (no migration needed).
--
-- All object creation uses IF NOT EXISTS / IF NOT EXISTS equivalent for idempotency.
-- ROLLBACK: see 089_rollback.sql
--
-- Run:
--   doppler run -- python -m dk_data.scripts.run_migration \
--     src/dk_data/sql/migrations/089_entity_linking_gaps.sql

-- Ensure hcs_raw schema exists before this migration runs.
-- hcs_raw is fully initialized by migration 114_cms_puf_platform_reconciliation.sql;
-- this guard makes 089 self-contained for CI environments where migrations run in order.
CREATE SCHEMA IF NOT EXISTS hcs_raw;

BEGIN;

-- ============================================================================
-- GAP 1: CMS Part D Prescriber PUF (new raw table)
-- Grain: (prscrbr_npi, gnrc_name, _source_year)
-- Source: CMS Medicare Part D Prescribers — by Provider and Drug
--         https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug
-- ============================================================================

CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber (
    id                      BIGSERIAL PRIMARY KEY,

    -- Provider identity (NPI is the canonical key)
    prscrbr_npi             TEXT NOT NULL,
    prscrbr_last_org_name   TEXT,
    prscrbr_first_name      TEXT,
    prscrbr_city            TEXT,
    prscrbr_state_abrvtn    TEXT,
    prscrbr_state_fips      TEXT,
    prscrbr_type            TEXT,           -- specialty description
    prscrbr_type_src        TEXT,           -- 'S' = specialty taxonomy, 'T' = claim-derived

    -- Drug (generic name = join key to mol_silver.molecule_aliases)
    gnrc_name               TEXT NOT NULL,
    brnd_name               TEXT,

    -- Utilization metrics
    tot_clms                BIGINT,
    tot_30day_fills         NUMERIC(18,2),
    tot_day_suply           BIGINT,
    tot_drug_cst            NUMERIC(18,2),
    tot_benes               INTEGER,

    -- 65+ beneficiary sub-metrics with CMS suppression flags
    -- ge65_sprsn_flag: 'Y' when <11 beneficiaries in 65+ cohort (metrics suppressed)
    ge65_sprsn_flag         TEXT,
    ge65_tot_clms           BIGINT,
    ge65_tot_30day_fills    NUMERIC(18,2),
    ge65_tot_drug_cst       NUMERIC(18,2),
    ge65_tot_day_suply      BIGINT,
    -- ge65_bene_sprsn_flag: 'Y' when beneficiary count is additionally suppressed
    ge65_bene_sprsn_flag    TEXT,
    ge65_tot_benes          INTEGER,

    -- Standard metadata (required on all hcs_raw tables)
    _source_year            INTEGER NOT NULL,
    _source_hash            TEXT NOT NULL,
    _source_file            TEXT,
    _loaded_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Uniqueness: one row per provider × drug × year
    UNIQUE (prscrbr_npi, gnrc_name, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_part_d_prescriber_npi
    ON hcs_raw.cms_part_d_prescriber (prscrbr_npi);
CREATE INDEX IF NOT EXISTS idx_cms_part_d_prescriber_gnrc
    ON hcs_raw.cms_part_d_prescriber (LOWER(gnrc_name));
CREATE INDEX IF NOT EXISTS idx_cms_part_d_prescriber_year
    ON hcs_raw.cms_part_d_prescriber (_source_year);

COMMENT ON TABLE hcs_raw.cms_part_d_prescriber IS
    'CMS Medicare Part D Prescribers by Provider and Drug. '
    'Grain: one row per prescriber NPI × generic drug name × source year. '
    'Enables query: which providers prescribe molecule X (via alias bridge). '
    'Feature: 020-entity-linking-gaps';

-- Register in meta.data_sources
-- Column set matches migration 083 schema: source_name, source_type, source_url,
-- description, refresh_frequency, is_active (no display_name or category columns)
INSERT INTO meta.data_sources (source_name, source_type, description, refresh_frequency, is_active)
VALUES (
    'cms_part_d_prescriber',
    'file',
    'CMS Medicare Part D Prescribers by Provider and Drug — NPI-level prescribing volume, '
    'spend, and beneficiary counts by generic drug name. Annual file.',
    'annual',
    TRUE
)
ON CONFLICT (source_name) DO UPDATE
    SET description        = EXCLUDED.description,
        refresh_frequency  = EXCLUDED.refresh_frequency,
        is_active          = TRUE;

-- ============================================================================
-- GAP 4: Open Payments — add drug name + NDC columns (1-5 slots)
-- CMS Open Payments General Payments file has up to 5 covered drug/biological
-- slots per payment record. These were absent from the original raw table.
-- ============================================================================

-- All ALTER TABLE statements for hcs_raw.cms_open_payments are guarded: in a fresh
-- CI/dev environment the table is created by migration 114; on an existing production
-- DB the table already exists and these column additions are applied.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'hcs_raw' AND table_name = 'cms_open_payments'
    ) THEN
        RETURN;  -- Table not yet created; migration 114 will include these columns.
    END IF;

    -- Drug name slots (exact CMS CSV column names)
    ALTER TABLE hcs_raw.cms_open_payments
        ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_1  TEXT,
        ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_2  TEXT,
        ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_3  TEXT,
        ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_4  TEXT,
        ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_5  TEXT;

    -- NDC slots
    ALTER TABLE hcs_raw.cms_open_payments
        ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_1  TEXT,
        ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_2  TEXT,
        ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_3  TEXT,
        ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_4  TEXT,
        ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_5  TEXT;

    -- record_id for upsert conflict key
    ALTER TABLE hcs_raw.cms_open_payments
        ADD COLUMN IF NOT EXISTS record_id  TEXT;

    -- Coverage/recipient fields and completeness columns
    ALTER TABLE hcs_raw.cms_open_payments
        ADD COLUMN IF NOT EXISTS covered_recipient_type              TEXT,
        ADD COLUMN IF NOT EXISTS payment_publication_date            DATE,
        ADD COLUMN IF NOT EXISTS program_year                        INTEGER,
        ADD COLUMN IF NOT EXISTS number_of_payments_included_in_total_amount INTEGER,
        ADD COLUMN IF NOT EXISTS form_of_payment_or_transfer_of_value TEXT,
        ADD COLUMN IF NOT EXISTS physician_first_name                TEXT,
        ADD COLUMN IF NOT EXISTS physician_last_name                 TEXT,
        ADD COLUMN IF NOT EXISTS physician_specialty                 TEXT,
        ADD COLUMN IF NOT EXISTS date_of_payment                     DATE,
        ADD COLUMN IF NOT EXISTS recipient_city                      TEXT,
        ADD COLUMN IF NOT EXISTS recipient_zip_code                  TEXT;

    -- Normalized drug name columns (generated, requires drug name columns above)
    ALTER TABLE hcs_raw.cms_open_payments
        ADD COLUMN IF NOT EXISTS drug_name_1_normalized  TEXT
            GENERATED ALWAYS AS (
                LOWER(REGEXP_REPLACE(name_of_drug_or_biological_or_device_or_medical_supply_1, '[^a-zA-Z0-9]', '', 'g'))
            ) STORED,
        ADD COLUMN IF NOT EXISTS drug_name_2_normalized  TEXT
            GENERATED ALWAYS AS (
                LOWER(REGEXP_REPLACE(name_of_drug_or_biological_or_device_or_medical_supply_2, '[^a-zA-Z0-9]', '', 'g'))
            ) STORED,
        ADD COLUMN IF NOT EXISTS drug_name_3_normalized  TEXT
            GENERATED ALWAYS AS (
                LOWER(REGEXP_REPLACE(name_of_drug_or_biological_or_device_or_medical_supply_3, '[^a-zA-Z0-9]', '', 'g'))
            ) STORED,
        ADD COLUMN IF NOT EXISTS drug_name_4_normalized  TEXT
            GENERATED ALWAYS AS (
                LOWER(REGEXP_REPLACE(name_of_drug_or_biological_or_device_or_medical_supply_4, '[^a-zA-Z0-9]', '', 'g'))
            ) STORED,
        ADD COLUMN IF NOT EXISTS drug_name_5_normalized  TEXT
            GENERATED ALWAYS AS (
                LOWER(REGEXP_REPLACE(name_of_drug_or_biological_or_device_or_medical_supply_5, '[^a-zA-Z0-9]', '', 'g'))
            ) STORED;

    -- Unique constraint for upsert idempotency
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'hcs_raw.cms_open_payments'::regclass
          AND conname  = 'cms_open_payments_record_id_year_key'
    ) THEN
        ALTER TABLE hcs_raw.cms_open_payments
            ADD CONSTRAINT cms_open_payments_record_id_year_key
            UNIQUE (record_id, _source_year);
    END IF;

    -- Index on normalized drug name for alias bridge join
    CREATE INDEX IF NOT EXISTS idx_open_payments_drug1_norm
        ON hcs_raw.cms_open_payments (drug_name_1_normalized)
        WHERE drug_name_1_normalized IS NOT NULL;

END $$;

COMMIT;

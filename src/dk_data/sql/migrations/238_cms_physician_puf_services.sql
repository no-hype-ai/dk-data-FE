-- Migration 238: CMS Physician PUF per-HCPCS services child table (Item 27c)
-- Feature: 006-claims-engine-data-gaps
-- New child table for per-HCPCS line items (the existing cms_physician_puf
-- captures only summary aggregates; this table captures procedure-level detail)

BEGIN;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_services (
    id                                              BIGSERIAL PRIMARY KEY,
    npi                                             TEXT NOT NULL,
    hcpcs_code                                      TEXT,
    hcpcs_description                               TEXT,
    place_of_service                                TEXT,
    number_of_services                              NUMERIC,
    number_of_medicare_beneficiaries                INTEGER,
    number_of_distinct_medicare_beneficiary_per_day_services NUMERIC,
    average_medicare_allowed_amt                    NUMERIC,
    average_submitted_charge_amt                    NUMERIC,
    average_medicare_payment_amt                    NUMERIC,
    average_medicare_standardized_amt               NUMERIC,
    ingested_at                                     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cms_physician_puf_services_npi
    ON hcs_raw.cms_physician_puf_services (npi);

CREATE INDEX IF NOT EXISTS idx_cms_physician_puf_services_hcpcs
    ON hcs_raw.cms_physician_puf_services (hcpcs_code);

DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON hcs_raw.cms_physician_puf_services TO mol_data_ops';
    END IF;
END $$;

COMMIT;

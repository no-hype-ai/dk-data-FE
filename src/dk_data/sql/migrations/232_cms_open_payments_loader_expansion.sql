-- Migration 232: CMS Open Payments Loader Expansion (Item 25, T021)
-- Feature: 006-claims-engine-data-gaps
--
-- Adds ~37 new columns to hcs_raw.cms_open_payments for full CMS Sunshine Act
-- coverage: physician NPI, teaching hospital fields, recipient geography,
-- dispute/publication metadata, manufacturer identity, product category/indication
-- slots, travel details, and flags.
--
-- All columns use ADD COLUMN IF NOT EXISTS for idempotency.

BEGIN;

-- Physician identity
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS physician_npi                          TEXT,
    ADD COLUMN IF NOT EXISTS physician_middle_name                  TEXT,
    ADD COLUMN IF NOT EXISTS physician_name_suffix                  TEXT,
    ADD COLUMN IF NOT EXISTS physician_primary_type                 TEXT,
    ADD COLUMN IF NOT EXISTS physician_specialty_2                  TEXT;

-- Teaching hospitals
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS teaching_hospital_ccn                  TEXT,
    ADD COLUMN IF NOT EXISTS teaching_hospital_id                   TEXT,
    ADD COLUMN IF NOT EXISTS teaching_hospital_name                 TEXT;

-- Recipient geography
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS recipient_country                                          TEXT,
    ADD COLUMN IF NOT EXISTS recipient_primary_business_street_address_line_1           TEXT,
    ADD COLUMN IF NOT EXISTS recipient_primary_business_street_address_line_2           TEXT,
    ADD COLUMN IF NOT EXISTS recipient_postal_code                                      TEXT,
    ADD COLUMN IF NOT EXISTS recipient_province                                         TEXT;

-- Publication / dispute metadata
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS dispute_status_for_publication         TEXT,
    ADD COLUMN IF NOT EXISTS delay_in_publication_indicator         TEXT,
    ADD COLUMN IF NOT EXISTS change_type                            TEXT,
    ADD COLUMN IF NOT EXISTS payment_publication_date               TEXT;

-- Manufacturer identity
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS applicable_manufacturer_or_applicable_gpo_making_payment_id      TEXT,
    ADD COLUMN IF NOT EXISTS applicable_manufacturer_or_applicable_gpo_making_payment_state    TEXT,
    ADD COLUMN IF NOT EXISTS applicable_manufacturer_or_applicable_gpo_making_payment_country  TEXT;

-- Product category / therapeutic area slots (1-5)
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS product_category_or_therapeutic_area_1 TEXT,
    ADD COLUMN IF NOT EXISTS product_category_or_therapeutic_area_2 TEXT,
    ADD COLUMN IF NOT EXISTS product_category_or_therapeutic_area_3 TEXT,
    ADD COLUMN IF NOT EXISTS product_category_or_therapeutic_area_4 TEXT,
    ADD COLUMN IF NOT EXISTS product_category_or_therapeutic_area_5 TEXT;

-- Product indication slots (1-5)
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS product_indication_1                  TEXT,
    ADD COLUMN IF NOT EXISTS product_indication_2                  TEXT,
    ADD COLUMN IF NOT EXISTS product_indication_3                  TEXT,
    ADD COLUMN IF NOT EXISTS product_indication_4                  TEXT,
    ADD COLUMN IF NOT EXISTS product_indication_5                  TEXT;

-- Travel details
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS city_of_travel                        TEXT,
    ADD COLUMN IF NOT EXISTS state_of_travel                       TEXT,
    ADD COLUMN IF NOT EXISTS country_of_travel                     TEXT;

-- Flags
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS physician_ownership_indicator          TEXT,
    ADD COLUMN IF NOT EXISTS third_party_payment_recipient_indicator TEXT,
    ADD COLUMN IF NOT EXISTS charity_indicator                      TEXT,
    ADD COLUMN IF NOT EXISTS contextual_information                 TEXT;

COMMIT;

-- Feature: 006-claims-engine-data-gaps (T025 + T028)
--
-- Adds missing columns to hcs_raw.cms_nppes to support ingestion of the full
-- ~330-column NPPES monthly dissemination file published at
-- https://download.cms.gov/nppes/NPI_Files.html
--
-- Column groups added (T025):
--   Taxonomy codes 3-15        : healthcare_provider_taxonomy_code_3..15       (13 cols)
--                                healthcare_provider_primary_taxonomy_switch_3..15 (13 cols)
--                                provider_license_number_3..15                 (13 cols)
--                                provider_license_number_state_code_3..15      (13 cols)
--                                = 52 columns via DO block
--
--   Other provider identifiers : other_provider_identifier_1..50               (50 cols)
--                                other_provider_identifier_type_code_1..50     (50 cols)
--                                other_provider_identifier_state_1..50         (50 cols)
--                                other_provider_identifier_issuer_1..50        (50 cols)
--                                = 200 columns via DO block
--
--   Practice location          : 8 columns (may already exist — IF NOT EXISTS)
--   Authorized official        : 7 columns
--   Deactivation               : npi_deactivation_reason_code + date cols
--   Entity-type                : is_sole_proprietor, is_organization_subpart,
--                                parent_organization_lbn, parent_organization_tin
--   Other                      : last_update_date, certification_date
--
-- Indexes added (T028):
--   idx_nppes_other_id_type_1..5 on (other_provider_identifier_type_code_N,
--                                     other_provider_identifier_N) for slots 1-5
--
-- Implementation notes:
--   - All ADD COLUMN use IF NOT EXISTS for idempotency
--   - DO blocks generate the repetitive 52 taxonomy and 200 identifier columns
--     programmatically to avoid 252 copy-pasted ALTER TABLE statements
--   - CONCURRENTLY indexes require running outside an explicit transaction;
--     T028 indexes run after COMMIT in a separate block
--   - Existing practice-location columns from the prior migration are covered
--     by IF NOT EXISTS — no double-apply risk

BEGIN;

SET LOCAL statement_timeout = '300s';
SET LOCAL lock_timeout = '20s';

-- ---------------------------------------------------------------------------
-- 1. Practice location (8 cols) — may already exist from earlier schema work
-- ---------------------------------------------------------------------------
ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS provider_first_line_business_practice_location_address     TEXT,
    ADD COLUMN IF NOT EXISTS provider_second_line_business_practice_location_address    TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_city_name      TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_state_name     TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_postal_code    TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_country_code   TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_telephone_number TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_fax_number     TEXT;

-- ---------------------------------------------------------------------------
-- 2. Authorized official (7 cols)
-- ---------------------------------------------------------------------------
ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS authorized_official_last_name          TEXT,
    ADD COLUMN IF NOT EXISTS authorized_official_first_name         TEXT,
    ADD COLUMN IF NOT EXISTS authorized_official_title_or_position  TEXT,
    ADD COLUMN IF NOT EXISTS authorized_official_telephone_number   TEXT,
    ADD COLUMN IF NOT EXISTS authorized_official_name_prefix_text   TEXT,
    ADD COLUMN IF NOT EXISTS authorized_official_name_suffix_text   TEXT,
    ADD COLUMN IF NOT EXISTS authorized_official_credential_text    TEXT;

-- ---------------------------------------------------------------------------
-- 3. Deactivation (3 cols — date cols already present; add reason code)
-- ---------------------------------------------------------------------------
ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS npi_deactivation_reason_code  TEXT,
    ADD COLUMN IF NOT EXISTS npi_deactivation_date         DATE,
    ADD COLUMN IF NOT EXISTS npi_reactivation_date         DATE;

-- ---------------------------------------------------------------------------
-- 4. Entity-type flags (4 cols)
-- ---------------------------------------------------------------------------
ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS is_sole_proprietor        TEXT,
    ADD COLUMN IF NOT EXISTS is_organization_subpart   TEXT,
    ADD COLUMN IF NOT EXISTS parent_organization_lbn   TEXT,
    ADD COLUMN IF NOT EXISTS parent_organization_tin   TEXT;

-- ---------------------------------------------------------------------------
-- 5. Timestamps (2 cols)
-- ---------------------------------------------------------------------------
ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS last_update_date    DATE,
    ADD COLUMN IF NOT EXISTS certification_date  DATE;

-- ---------------------------------------------------------------------------
-- 6. Taxonomy codes 3-15 — 52 columns via DO block
--    Generates: healthcare_provider_taxonomy_code_N,
--               healthcare_provider_primary_taxonomy_switch_N,
--               provider_license_number_N,
--               provider_license_number_state_code_N
--    for N in 3..15
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    i INT;
BEGIN
    FOR i IN 3..15 LOOP
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS healthcare_provider_taxonomy_code_%s TEXT',
            i
        );
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS healthcare_provider_primary_taxonomy_switch_%s TEXT',
            i
        );
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS provider_license_number_%s TEXT',
            i
        );
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS provider_license_number_state_code_%s TEXT',
            i
        );
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. Other provider identifiers 1-50 — 200 columns via DO block
--    Generates: other_provider_identifier_N,
--               other_provider_identifier_type_code_N,
--               other_provider_identifier_state_N,
--               other_provider_identifier_issuer_N
--    for N in 1..50
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    i INT;
BEGIN
    FOR i IN 1..50 LOOP
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS other_provider_identifier_%s TEXT',
            i
        );
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS other_provider_identifier_type_code_%s TEXT',
            i
        );
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS other_provider_identifier_state_%s TEXT',
            i
        );
        EXECUTE format(
            'ALTER TABLE hcs_raw.cms_nppes ADD COLUMN IF NOT EXISTS other_provider_identifier_issuer_%s TEXT',
            i
        );
    END LOOP;
END;
$$;

COMMIT;

-- ---------------------------------------------------------------------------
-- T028: Indexes on other_provider_identifier slots 1-5
-- CREATE INDEX CONCURRENTLY cannot run inside a transaction block, so these
-- are issued after COMMIT. Each index covers (type_code, identifier) to
-- support type-filtered identifier lookups from silver entity resolution.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nppes_other_id_type_1
    ON hcs_raw.cms_nppes (other_provider_identifier_type_code_1, other_provider_identifier_1);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nppes_other_id_type_2
    ON hcs_raw.cms_nppes (other_provider_identifier_type_code_2, other_provider_identifier_2);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nppes_other_id_type_3
    ON hcs_raw.cms_nppes (other_provider_identifier_type_code_3, other_provider_identifier_3);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nppes_other_id_type_4
    ON hcs_raw.cms_nppes (other_provider_identifier_type_code_4, other_provider_identifier_4);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nppes_other_id_type_5
    ON hcs_raw.cms_nppes (other_provider_identifier_type_code_5, other_provider_identifier_5);

-- SQLMesh Model: Silver Physician Profiles
-- Promotes mol_bronze.npi_registry into mol_silver.physician_profiles.
-- NPI Registry (NPPES): physician identity, specialty (taxonomy), practice location.
-- Used by xenon assessment pipeline for KOL/HCP profiling (path: /physician_profiles).
-- Note: no molecule_id — profiles are person-level, not drug-level.

MODEL (
    name mol_silver.physician_profiles,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key npi
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi)),
        unique_values(columns := (npi))
    ),
    grain npi
);

SELECT
    gen_random_uuid()           AS id,
    b.npi,
    b.provider_type,
    b.first_name,
    b.last_name,
    b.organization_name,
    -- Full name (individuals) or organisation
    CASE
        WHEN b.last_name IS NOT NULL
        THEN TRIM(COALESCE(b.first_name, '') || ' ' || b.last_name)
        ELSE b.organization_name
    END                         AS display_name,
    b.credential,
    b.gender,
    b.status,
    b.enumeration_date,
    -- Primary taxonomy / specialty
    b.taxonomy_code,
    b.taxonomy_description       AS specialty,
    b.is_primary_taxonomy,
    b.license_state,
    b.license_number,
    -- Practice location
    b.practice_city,
    b.practice_state,
    b.practice_zip,
    b.practice_country,
    -- Full structured arrays carried forward
    b.taxonomies,
    b.addresses,
    'npi_registry'              AS source,
    b.source_updated_at,
    NOW()                       AS created_at

FROM mol_bronze.npi_registry b
WHERE b.npi IS NOT NULL;

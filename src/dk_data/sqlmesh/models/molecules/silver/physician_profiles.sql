-- SQLMesh Model: Silver Physician Profiles
-- Unified NPI entity registry bridging hcs_silver.provider_profile (canonical) and
-- mol_bronze.npi_registry (credential/license/taxonomy enrichment).
--
-- Design:
--   Primary source : hcs_silver.provider_profile (latest year per NPI) — authoritative entity hub.
--                    Provides utilization data, taxonomy codes, specialty, location.
--   Enrichment     : mol_bronze.npi_registry — credential, license, full taxonomy/address arrays.
--                    Deduplicated to one row per NPI (most recent source_updated_at).
--   Supplement     : mol_bronze.npi_registry NPIs not present in hcs_silver (non-Medicare providers).
--
-- Downstream: xenon assessment pipeline for KOL/HCP profiling (path: /physician_profiles).
-- Feature: 019-cms-puf-platform-reconciliation (HCP entity consolidation)
--
-- CROSS-DOMAIN NOTE: Intentionally reads from hcs_silver.provider_profile to merge
-- HCS provider data with molecule-domain NPI records. This is an approved exception
-- to the "silver reads only from bronze" rule.

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

-- Latest year per NPI from the canonical entity hub
WITH latest_hcs AS (
    SELECT DISTINCT ON (npi) *
    FROM hcs_silver.provider_profile
    ORDER BY npi, _source_year DESC
),

-- Deduplicated mol_bronze.npi_registry: one row per NPI, most recent ingestion
mol_npi AS (
    SELECT DISTINCT ON (npi)
        npi,
        provider_type,
        first_name,
        last_name,
        organization_name,
        credential,
        gender,
        status,
        enumeration_date,
        taxonomy_code,
        taxonomy_description,
        is_primary_taxonomy,
        primary_taxonomy_code,
        taxonomy_codes,
        license_state,
        license_number,
        practice_city,
        practice_state,
        practice_zip,
        practice_country,
        taxonomies,
        addresses,
        source_updated_at
    FROM mol_bronze.npi_registry
    WHERE npi IS NOT NULL
    ORDER BY npi, source_updated_at DESC NULLS LAST
),

-- Merged view: hcs_silver (primary) LEFT JOIN mol_npi (enrichment)
hcs_enriched AS (
    SELECT
        h.npi,
        h.canonical_name,
        -- Structured name fields from mol_bronze when available
        COALESCE(r.first_name, '') AS first_name,
        r.last_name,
        r.organization_name,
        h.provider_entity_type           AS provider_type,
        h.specialty,
        r.credential,
        r.gender,
        r.status,
        r.enumeration_date,
        -- Taxonomy: prefer hcs_silver (multi-source), fall back to mol_bronze
        COALESCE(h.taxonomy_code_1, r.taxonomy_code)                         AS taxonomy_code,
        h.taxonomy_code_2,
        r.taxonomy_description,
        r.is_primary_taxonomy,
        COALESCE(r.primary_taxonomy_code, h.taxonomy_code_1)                  AS primary_taxonomy_code,
        COALESCE(r.taxonomy_codes, ARRAY[h.taxonomy_code_1]::TEXT[])          AS taxonomy_codes,
        r.license_state,
        r.license_number,
        -- Location: hcs_silver is primary (Physician PUF + NPPES)
        h.city                           AS practice_city,
        h.state                          AS practice_state,
        h.zip_code                       AS practice_zip,
        r.practice_country,
        -- Full arrays only from mol_bronze
        r.taxonomies,
        r.addresses,
        -- Provider status
        h.is_deactivated,
        h.npi_deactivation_date,
        h.npi_reactivation_date,
        h.medicare_participation_indicator,
        -- Utilization (from hcs entity hub)
        h.total_services,
        h.total_unique_benes,
        h.total_medicare_payment_amt,
        h.total_medicare_allowed_amt,
        h.total_submitted_chrg_amt,
        -- Data quality
        h.data_completeness_score,
        h.data_sources,
        'hcs_provider_profile'           AS primary_source,
        GREATEST(r.source_updated_at, h.updated_at) AS source_updated_at
    FROM latest_hcs h
    LEFT JOIN mol_npi r ON r.npi = h.npi
    WHERE h.canonical_name IS NOT NULL
      AND LENGTH(TRIM(h.canonical_name)) > 0
),

-- Supplement: mol_bronze NPIs not already in hcs_silver (non-Medicare / NPPES-only providers)
mol_only AS (
    SELECT
        r.npi,
        CASE
            WHEN r.last_name IS NOT NULL
            THEN TRIM(COALESCE(r.first_name, '') || ' ' || r.last_name)
            ELSE r.organization_name
        END                              AS canonical_name,
        COALESCE(r.first_name, '')       AS first_name,
        r.last_name,
        r.organization_name,
        r.provider_type,
        r.taxonomy_description           AS specialty,
        r.credential,
        r.gender,
        r.status,
        r.enumeration_date,
        r.taxonomy_code,
        NULL::TEXT                       AS taxonomy_code_2,
        r.taxonomy_description,
        r.is_primary_taxonomy,
        r.primary_taxonomy_code,
        r.taxonomy_codes,
        r.license_state,
        r.license_number,
        r.practice_city,
        r.practice_state,
        r.practice_zip,
        r.practice_country,
        r.taxonomies,
        r.addresses,
        FALSE                            AS is_deactivated,
        NULL::DATE                       AS npi_deactivation_date,
        NULL::DATE                       AS npi_reactivation_date,
        NULL::TEXT                       AS medicare_participation_indicator,
        NULL::NUMERIC                    AS total_services,
        NULL::NUMERIC                    AS total_unique_benes,
        NULL::NUMERIC                    AS total_medicare_payment_amt,
        NULL::NUMERIC                    AS total_medicare_allowed_amt,
        NULL::NUMERIC                    AS total_submitted_chrg_amt,
        0.5::NUMERIC                     AS data_completeness_score,
        ARRAY['npi_registry']::TEXT[]    AS data_sources,
        'npi_registry'                   AS primary_source,
        r.source_updated_at
    FROM mol_npi r
    WHERE NOT EXISTS (
        SELECT 1 FROM latest_hcs h WHERE h.npi = r.npi
    )
)

SELECT
    gen_random_uuid()   AS id,
    npi,
    canonical_name,
    first_name,
    last_name,
    organization_name,
    provider_type,
    specialty,
    credential,
    gender,
    status,
    enumeration_date,
    taxonomy_code,
    taxonomy_code_2,
    taxonomy_description,
    is_primary_taxonomy,
    primary_taxonomy_code,
    taxonomy_codes,
    license_state,
    license_number,
    practice_city,
    practice_state,
    practice_zip,
    practice_country,
    taxonomies,
    addresses,
    is_deactivated,
    npi_deactivation_date,
    npi_reactivation_date,
    medicare_participation_indicator,
    total_services,
    total_unique_benes,
    total_medicare_payment_amt,
    total_medicare_allowed_amt,
    total_submitted_chrg_amt,
    data_completeness_score,
    data_sources,
    primary_source,
    source_updated_at,
    NOW()               AS created_at
FROM hcs_enriched

UNION ALL

SELECT
    gen_random_uuid()   AS id,
    npi,
    canonical_name,
    first_name,
    last_name,
    organization_name,
    provider_type,
    specialty,
    credential,
    gender,
    status,
    enumeration_date,
    taxonomy_code,
    taxonomy_code_2,
    taxonomy_description,
    is_primary_taxonomy,
    primary_taxonomy_code,
    taxonomy_codes,
    license_state,
    license_number,
    practice_city,
    practice_state,
    practice_zip,
    practice_country,
    taxonomies,
    addresses,
    is_deactivated,
    npi_deactivation_date,
    npi_reactivation_date,
    medicare_participation_indicator,
    total_services,
    total_unique_benes,
    total_medicare_payment_amt,
    total_medicare_allowed_amt,
    total_submitted_chrg_amt,
    data_completeness_score,
    data_sources,
    primary_source,
    source_updated_at,
    NOW()               AS created_at
FROM mol_only;

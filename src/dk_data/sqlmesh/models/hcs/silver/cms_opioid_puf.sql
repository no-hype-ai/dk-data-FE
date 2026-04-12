-- SQLMesh Model: hcs_silver.cms_opioid_puf
-- NPI-level opioid prescribing PUF with molecule linkage via molecule_names hub.
--
-- Source: hcs_bronze.cms_opioid_puf
-- Bronze has no NDC column — molecule linkage uses drug name path only:
--   Tier 1: gnrc_name → mol_silver.molecule_names (name_kind='generic', equi-join)
--   Tier 2: brnd_name → mol_silver.molecule_names (name_kind IN ('brand','canonical'))
--
-- Provider linkage:
--   prscrbr_npi → hcs_silver.provider_identifiers (source='npi') → provider_id
--
-- Grain: (prscrbr_npi, gnrc_name, _source_year)
--
-- Feature: 001-silver-medallion-rebuild

MODEL (
    name hcs_silver.cms_opioid_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (prscrbr_npi, gnrc_name, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (prscrbr_npi, gnrc_name, _source_year),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT
    gen_random_uuid()               AS id,

    -- Provider identity
    b.prscrbr_npi,
    b.prscrbr_last_org_name,
    b.prscrbr_first_name,
    b.prscrbr_city,
    b.prscrbr_state_abrvtn,
    b.prscrbr_state_fips,
    b.prscrbr_type,
    b.prscrbr_type_src,

    -- Provider hub linkage
    prov_link.provider_id,

    -- Drug names
    b.gnrc_name,
    b.brnd_name,

    -- Molecule hub linkage (generic preferred, brand fallback)
    COALESCE(mol_generic.molecule_id, mol_brand.molecule_id) AS molecule_id,
    CASE
        WHEN mol_generic.molecule_id IS NOT NULL THEN 0.85
        WHEN mol_brand.molecule_id   IS NOT NULL THEN 0.70
        ELSE NULL
    END                             AS link_confidence,
    CASE
        WHEN mol_generic.molecule_id IS NOT NULL THEN 'generic'
        WHEN mol_brand.molecule_id   IS NOT NULL THEN 'brand'
        ELSE NULL
    END                             AS link_strategy,
    CASE
        WHEN COALESCE(mol_generic.molecule_id, mol_brand.molecule_id) IS NOT NULL
        THEN TRUE ELSE FALSE
    END                             AS molecule_resolved,

    -- Opioid classification flags
    b.opioid_drug_flag,
    b.la_opioid_drug_flag,

    -- Utilization metrics
    b.tot_clms,
    b.tot_30day_fills,
    b.tot_day_suply,
    b.tot_drug_cst,
    b.tot_benes,

    -- Opioid-specific metrics
    b.opioid_clms,
    b.opioid_benes,
    b.la_opioid_clms,
    b.la_opioid_benes,

    -- Source tracking
    b._source_year,
    b._source_hash,

    NOW()                           AS created_at,
    NOW()                           AS updated_at

FROM hcs_bronze.cms_opioid_puf b

-- Tier 1: generic name → mol_silver.molecule_names (LIMIT 1 prevents fan-out)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE b.gnrc_name IS NOT NULL
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(b.gnrc_name, '[^a-zA-Z0-9]', '', 'g'))
      AND mn.name_kind = 'generic'
    ORDER BY mn.molecule_id
    LIMIT 1
) mol_generic ON TRUE

-- Tier 2: brand name fallback → mol_silver.molecule_names
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE mol_generic.molecule_id IS NULL
      AND b.brnd_name IS NOT NULL
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(b.brnd_name, '[^a-zA-Z0-9]', '', 'g'))
      AND mn.name_kind IN ('brand', 'canonical')
    ORDER BY mn.molecule_id
    LIMIT 1
) mol_brand ON TRUE

-- Provider hub: NPI → provider_id
LEFT JOIN LATERAL (
    SELECT pi.provider_id
    FROM hcs_silver.provider_identifiers pi
    WHERE pi.source = 'npi'
      AND pi.identifier = b.prscrbr_npi::TEXT
    LIMIT 1
) prov_link ON TRUE;

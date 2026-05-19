-- SQLMesh Model: hcs_silver.part_d_prescribing
-- NPI-level Part D prescribing linked to mol_silver.molecules via molecule_names hub.
--
-- Closes Gap 1 from ENTITY_LINKING_STRATEGY.md:
--   "NPI-level Part D prescribing not in silver — Cannot query 'prescribers of drug X'"
--
-- Entity linking strategy (tiered):
--   Tier 1 (generic name, confidence 0.85):
--     gnrc_name → mol_silver.molecule_names (normalized_name, name_kind='generic')
--     CMS generic names are controlled vocabulary — high confidence.
--   Tier 2 (brand name fallback, confidence 0.70):
--     brnd_name → mol_silver.molecule_names (normalized_name, name_kind IN ('brand','canonical'))
--
-- NPI linking:
--   prscrbr_npi → hcs_silver.provider_identifiers (source='npi') → provider_id
--
-- Grain: (prscrbr_npi, gnrc_name, _source_year)
--   gnrc_name is kept alongside molecule_id so rows with no match
--   (unresolved drugs) are still preserved — they appear with molecule_id = NULL.
--
-- Feature: 001-silver-medallion-rebuild (updated from 020-entity-linking-gaps)

MODEL (
    name hcs_silver.part_d_prescribing,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (prscrbr_npi, gnrc_name, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (prscrbr_npi, gnrc_name, _source_year))
    ),
    grain (prscrbr_npi, gnrc_name, _source_year)
);

SELECT
    gen_random_uuid()                   AS id,

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

    -- Drug (both raw name and resolved molecule)
    b.gnrc_name,
    b.brnd_name,
    -- Tier 1 generic preferred; Tier 2 brand fallback
    COALESCE(mol_generic.molecule_id, mol_brand.molecule_id) AS molecule_id,
    CASE
        WHEN mol_generic.molecule_id IS NOT NULL THEN 0.85
        WHEN mol_brand.molecule_id   IS NOT NULL THEN 0.70
        ELSE NULL
    END                                 AS link_confidence,
    CASE
        WHEN mol_generic.molecule_id IS NOT NULL THEN 'generic'
        WHEN mol_brand.molecule_id   IS NOT NULL THEN 'brand'
        ELSE NULL
    END                                 AS matched_alias_type,

    -- Utilization metrics
    b.tot_clms,
    b.tot_30day_fills,
    b.tot_day_suply,
    b.tot_drug_cst,
    b.tot_benes,

    -- 65+ sub-metrics with CMS suppression flags
    b.ge65_sprsn_flag,
    b.ge65_tot_clms,
    b.ge65_tot_30day_fills,
    b.ge65_tot_drug_cst,
    b.ge65_tot_day_suply,
    b.ge65_bene_sprsn_flag,
    b.ge65_tot_benes,

    -- Source year dimension
    b._source_year,
    b._source_hash,

    -- Data quality: was the molecule resolved?
    CASE
        WHEN COALESCE(mol_generic.molecule_id, mol_brand.molecule_id) IS NOT NULL
        THEN TRUE ELSE FALSE
    END                                 AS molecule_resolved,

    NOW()                               AS created_at,
    NOW()                               AS updated_at

FROM hcs_bronze.cms_part_d_prescriber b

-- Tier 1: generic name → molecule_names (name_kind='generic', LIMIT 1 prevents fan-out)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE b.gnrc_name IS NOT NULL
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(b.gnrc_name, '[^a-zA-Z0-9]', '', 'g'))
      AND mn.name_kind = 'generic'
    ORDER BY mn.molecule_id
    LIMIT 1
) mol_generic ON TRUE

-- Tier 2: brand name fallback → molecule_names (name_kind IN ('brand','canonical'))
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
) prov_link ON TRUE

WHERE b.prscrbr_npi IS NOT NULL
  AND b.gnrc_name IS NOT NULL;

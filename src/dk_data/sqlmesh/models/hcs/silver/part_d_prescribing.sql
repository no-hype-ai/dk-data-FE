-- SQLMesh Model: hcs_silver.part_d_prescribing
-- NPI-level Part D prescribing linked to mol_silver.molecules via alias bridge.
--
-- Closes Gap 1 from ENTITY_LINKING_STRATEGY.md:
--   "NPI-level Part D prescribing not in silver — Cannot query 'prescribers of drug X'"
--
-- Entity linking strategy:
--   gnrc_name (generic drug name, already lowercased by loader) →
--   mol_silver.molecule_aliases (alias_name_normalized) → molecule_id
--   Confidence: 0.85 (generic name is a controlled vocabulary at CMS, not free text)
--
-- NPI linking:
--   prscrbr_npi → hcs_silver.provider_profile (left join — profile may not exist
--   for all years; prescriber data predates NPPES in some vintages)
--
-- Grain: (prscrbr_npi, molecule_id, gnrc_name, _source_year)
--   gnrc_name is kept alongside molecule_id so rows with no alias match
--   (unresolved drugs) are still preserved — they appear with molecule_id = NULL.
--
-- Feature: 020-entity-linking-gaps

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

-- ── Prescriber-drug records from bronze ──────────────────────────────────────
WITH prescriber_drug AS (
    SELECT
        prscrbr_npi,
        prscrbr_last_org_name,
        prscrbr_first_name,
        prscrbr_city,
        prscrbr_state_abrvtn,
        prscrbr_state_fips,
        prscrbr_type,
        prscrbr_type_src,
        brnd_name,
        gnrc_name,
        tot_clms,
        tot_30day_fills,
        tot_day_suply,
        tot_drug_cst,
        tot_benes,
        ge65_sprsn_flag,
        ge65_tot_clms,
        ge65_tot_30day_fills,
        ge65_tot_drug_cst,
        ge65_tot_day_suply,
        ge65_bene_sprsn_flag,
        ge65_tot_benes,
        _source_year
    FROM hcs_bronze.cms_part_d_prescriber
    WHERE prscrbr_npi IS NOT NULL
      AND gnrc_name IS NOT NULL
),

-- ── Molecule alias lookup: generic name → molecule_id ────────────────────────
-- gnrc_name is already lowercased by the loader validator (normalize_gnrc_name).
-- alias_name_normalized strips all non-alphanumeric chars and lowercases.
-- We match on the stripped form of gnrc_name for maximum recall.
drug_molecule AS (
    SELECT DISTINCT
        pd.gnrc_name,
        ma.molecule_id,
        -- Confidence: CMS generic names are controlled vocabulary (high quality)
        0.85 AS link_confidence,
        -- Prefer the alias that matched most closely (canonical > synonym > brand)
        FIRST_VALUE(ma.alias_type) OVER (
            PARTITION BY pd.gnrc_name
            ORDER BY
                CASE ma.alias_type
                    WHEN 'canonical' THEN 1
                    WHEN 'generic'   THEN 2
                    WHEN 'synonym'   THEN 3
                    ELSE                  4
                END
        ) AS matched_alias_type
    FROM (SELECT DISTINCT gnrc_name FROM prescriber_drug) pd
    JOIN mol_silver.molecule_aliases ma
        ON LOWER(REGEXP_REPLACE(pd.gnrc_name, '[^a-zA-Z0-9]', '', 'g'))
         = ma.alias_name_normalized
),

-- Deduplicate: one molecule_id per gnrc_name (pick highest-priority alias type)
drug_molecule_deduped AS (
    SELECT DISTINCT ON (gnrc_name)
        gnrc_name,
        molecule_id,
        link_confidence,
        matched_alias_type
    FROM drug_molecule
    ORDER BY gnrc_name,
             CASE matched_alias_type
                 WHEN 'canonical' THEN 1
                 WHEN 'generic'   THEN 2
                 WHEN 'synonym'   THEN 3
                 ELSE                  4
             END
)

-- ── Final output: prescriber × drug × year with molecule linkage ─────────────
SELECT
    gen_random_uuid()                   AS id,

    -- Provider identity
    pd.prscrbr_npi,
    pd.prscrbr_last_org_name,
    pd.prscrbr_first_name,
    pd.prscrbr_city,
    pd.prscrbr_state_abrvtn,
    pd.prscrbr_state_fips,
    pd.prscrbr_type,
    pd.prscrbr_type_src,

    -- Drug (both raw name and resolved molecule)
    pd.gnrc_name,
    pd.brnd_name,
    dm.molecule_id,                                     -- NULL if alias not found
    dm.link_confidence,                                 -- NULL if no link
    dm.matched_alias_type,                              -- NULL if no link

    -- Utilization metrics
    pd.tot_clms,
    pd.tot_30day_fills,
    pd.tot_day_suply,
    pd.tot_drug_cst,
    pd.tot_benes,

    -- 65+ sub-metrics with CMS suppression flags
    -- ge65_sprsn_flag = 'Y' when <11 beneficiaries in 65+ cohort (metrics are NULL)
    pd.ge65_sprsn_flag,
    pd.ge65_tot_clms,
    pd.ge65_tot_30day_fills,
    pd.ge65_tot_drug_cst,
    pd.ge65_tot_day_suply,
    -- ge65_bene_sprsn_flag = 'Y' when beneficiary count is additionally suppressed
    pd.ge65_bene_sprsn_flag,
    pd.ge65_tot_benes,

    -- Source year dimension
    pd._source_year,

    -- Data quality: was the molecule resolved?
    CASE WHEN dm.molecule_id IS NOT NULL THEN TRUE ELSE FALSE END AS molecule_resolved,

    NOW()                               AS created_at,
    NOW()                               AS updated_at

FROM prescriber_drug pd
LEFT JOIN drug_molecule_deduped dm ON pd.gnrc_name = dm.gnrc_name;

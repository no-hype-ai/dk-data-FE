-- SQLMesh Model: Silver Molecule Aliases
-- Aggregated molecule name aliases from all sources
-- Used for fuzzy name matching with pg_trgm
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_silver.molecule_aliases,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, alias_name_normalized)
    ),
    cron '@daily',
    grain (molecule_id, alias_name_normalized),
    columns (
        molecule_id UUID,
        alias_name TEXT,
        alias_name_normalized TEXT,
        alias_type TEXT,
        source TEXT,
        created_at TIMESTAMPTZ
    ),
    audits (
        not_null(columns := (molecule_id)),
        not_null(columns := (alias_name))
    ),
    -- T172: Large multi-source alias table with jsonb_array_elements + DISTINCT ON — set work_mem
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Collect aliases from all sources, then deduplicate on (molecule_id, alias_name_normalized).
-- INCREMENTAL_BY_UNIQUE_KEY uses MERGE; a MERGE fails (CardinalityViolation) if the source
-- batch contains two rows with the same unique key. The DISTINCT ON below ensures at most one
-- row per (molecule_id, alias_name_normalized) by keeping the highest-priority alias_type.
WITH all_aliases AS (

    -- Canonical names from mol_silver.molecules
    -- Includes all molecules (small molecules, biologics, DrugBank-source) so that
    -- downstream name-based lookups (clinical_trials, drug_labels, etc.) can find any entry.
    SELECT
        m.molecule_id,
        m.canonical_name AS alias_name,
        LOWER(REGEXP_REPLACE(m.canonical_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'canonical' AS alias_type,
        m.primary_source AS source
    FROM mol_silver.molecules m
    WHERE m.canonical_name IS NOT NULL

    UNION ALL

    -- ChEMBL synonyms
    -- c.synonyms is [{"molecule_synonym": "Gleevec", "syn_type": "TRADE_NAME"}, ...] (raw API format).
    -- Must use jsonb_array_elements (not _text) and extract ->>'molecule_synonym'.
    -- Join handles both structural (inchi_key match) and biologic (name match, inchi_key IS NULL)
    SELECT
        m.molecule_id,
        syn_obj->>'molecule_synonym' AS alias_name,
        LOWER(REGEXP_REPLACE(syn_obj->>'molecule_synonym', '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'synonym' AS alias_type,
        'chembl' AS source
    FROM mol_silver.molecules m
    JOIN mol_bronze.chembl_molecules c ON (
        (m.inchi_key IS NOT NULL AND m.inchi_key = c.inchi_key)
        OR (m.inchi_key IS NULL AND LOWER(m.canonical_name) = LOWER(c.pref_name))
    )
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(c.synonyms, '[]'::jsonb)) AS syn_obj
    WHERE syn_obj->>'molecule_synonym' IS NOT NULL
      AND syn_obj->>'molecule_synonym' != ''

    UNION ALL

    -- DrugBank synonyms
    -- NOTE: mol_bronze.drugbank.synonyms populated from JSONB synonyms field in XML fetcher.
    SELECT
        m.molecule_id,
        syn AS alias_name,
        LOWER(REGEXP_REPLACE(syn, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'synonym' AS alias_type,
        'drugbank' AS source
    FROM mol_silver.molecules m
    JOIN mol_bronze.drugbank d ON LOWER(m.canonical_name) = LOWER(d.name)
    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(d.synonyms, '[]'::JSONB)) AS syn
    WHERE syn IS NOT NULL
      AND syn != ''
      AND d.name IS NOT NULL

    UNION ALL

    -- DrugBank brand names (international_brands)
    SELECT
        m.molecule_id,
        brand->>'name' AS alias_name,
        LOWER(REGEXP_REPLACE(brand->>'name', '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'brand' AS alias_type,
        'drugbank' AS source
    FROM mol_silver.molecules m
    JOIN mol_bronze.drugbank d ON LOWER(m.canonical_name) = LOWER(d.name)
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(d.international_brands, '[]'::JSONB)) AS brand
    WHERE brand->>'name' IS NOT NULL
      AND brand->>'name' != ''
      AND d.name IS NOT NULL

    UNION ALL

    -- FDA drug label brand names
    SELECT
        m.molecule_id,
        dl.brand_name AS alias_name,
        LOWER(REGEXP_REPLACE(dl.brand_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'brand' AS alias_type,
        'openfda' AS source
    FROM mol_silver.molecules m
    JOIN mol_silver.drug_labels dl ON m.molecule_id = dl.molecule_id
    WHERE dl.brand_name IS NOT NULL
      AND dl.brand_name != ''

    UNION ALL

    -- FDA drug label generic names
    SELECT
        m.molecule_id,
        dl.generic_name AS alias_name,
        LOWER(REGEXP_REPLACE(dl.generic_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'generic' AS alias_type,
        'openfda' AS source
    FROM mol_silver.molecules m
    JOIN mol_silver.drug_labels dl ON m.molecule_id = dl.molecule_id
    WHERE dl.generic_name IS NOT NULL
      AND dl.generic_name != ''

    UNION ALL

    -- PubChem synonyms
    -- p.synonyms is now a JSONB string array ["aspirin", "Anacin", ...]
    -- populated by load_pubchem_extended.py --synonyms from the PubChem synonym endpoint.
    -- Empty array until synonyms are loaded; produces 0 rows but does not break.
    SELECT
        m.molecule_id,
        syn AS alias_name,
        LOWER(REGEXP_REPLACE(syn, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'synonym' AS alias_type,
        'pubchem' AS source
    FROM mol_silver.molecules m
    JOIN mol_bronze.pubchem p ON m.inchi_key = p.inchi_key
    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(p.synonyms, '[]'::jsonb)) AS syn
    WHERE syn IS NOT NULL
      AND syn != ''

    UNION ALL

    -- Clinical trial intervention names (unnest JSONB array; match DRUG-type interventions by name)
    SELECT DISTINCT
        m.molecule_id,
        interv->>'name' AS alias_name,
        LOWER(REGEXP_REPLACE(interv->>'name', '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'trial_intervention' AS alias_type,
        'clinicaltrials' AS source
    FROM mol_silver.clinical_trials ct
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(ct.interventions, '[]'::jsonb)) AS interv
    JOIN mol_silver.molecules m
        ON interv->>'type' = 'DRUG'
       AND LOWER(m.canonical_name) = LOWER(interv->>'name')
    WHERE interv->>'name' IS NOT NULL
      AND interv->>'name' != ''

    UNION ALL

    -- Orange Book trade names (join directly on canonical_name = ingredient, no self-reference)
    SELECT DISTINCT
        m.molecule_id,
        ob.trade_name AS alias_name,
        LOWER(REGEXP_REPLACE(ob.trade_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
        'trade' AS alias_type,
        'orangebook' AS source
    FROM mol_silver.molecules m
    JOIN mol_bronze.orange_book ob ON LOWER(m.canonical_name) = LOWER(ob.ingredient)
    WHERE ob.trade_name IS NOT NULL
      AND ob.trade_name != ''

),

-- Deduplicate on (molecule_id, alias_name_normalized); priority: canonical > synonym > generic > brand > trade > product > trial_intervention
deduped AS (
    SELECT DISTINCT ON (molecule_id, alias_name_normalized)
        molecule_id,
        alias_name,
        alias_name_normalized,
        alias_type,
        source
    FROM all_aliases
    WHERE alias_name_normalized IS NOT NULL AND alias_name_normalized != ''
    ORDER BY molecule_id, alias_name_normalized,
        CASE alias_type
            WHEN 'canonical'          THEN 1
            WHEN 'synonym'            THEN 2
            WHEN 'generic'            THEN 3
            WHEN 'brand'              THEN 4
            WHEN 'trade'              THEN 5
            WHEN 'trial_intervention' THEN 6
            ELSE 7
        END
)

SELECT
    molecule_id,
    alias_name,
    alias_name_normalized,
    alias_type,
    source,
    NOW() AS created_at
FROM deduped;

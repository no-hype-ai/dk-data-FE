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
    )
);

-- Collect aliases from all sources

-- Canonical names from silver.molecules
SELECT
    m.id AS molecule_id,
    m.canonical_name AS alias_name,
    LOWER(REGEXP_REPLACE(m.canonical_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'canonical' AS alias_type,
    m.primary_source AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
WHERE m.canonical_name IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- ChEMBL synonyms
SELECT
    m.id AS molecule_id,
    syn AS alias_name,
    LOWER(REGEXP_REPLACE(syn, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'synonym' AS alias_type,
    'chembl' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN bronze.chembl_molecules c ON m.inchi_key = c.inchi_key
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(c.synonyms, '[]'::jsonb)) AS syn
WHERE syn IS NOT NULL
  AND syn != ''
  AND m.needs_review = FALSE

UNION ALL

-- DrugBank synonyms
SELECT
    m.id AS molecule_id,
    syn AS alias_name,
    LOWER(REGEXP_REPLACE(syn, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'synonym' AS alias_type,
    'drugbank' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN bronze.drugbank d ON m.inchi_key = d.inchi_key
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(d.synonyms, '[]'::jsonb)) AS syn
WHERE syn IS NOT NULL
  AND syn != ''
  AND m.needs_review = FALSE

UNION ALL

-- DrugBank brand names
SELECT
    m.id AS molecule_id,
    brand->>'name' AS alias_name,
    LOWER(REGEXP_REPLACE(brand->>'name', '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'brand' AS alias_type,
    'drugbank' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN bronze.drugbank d ON m.inchi_key = d.inchi_key
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(d.international_brands, '[]'::jsonb)) AS brand
WHERE brand->>'name' IS NOT NULL
  AND brand->>'name' != ''
  AND m.needs_review = FALSE

UNION ALL

-- DrugBank product names
SELECT
    m.id AS molecule_id,
    prod->>'name' AS alias_name,
    LOWER(REGEXP_REPLACE(prod->>'name', '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'product' AS alias_type,
    'drugbank' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN bronze.drugbank d ON m.inchi_key = d.inchi_key
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(d.products, '[]'::jsonb)) AS prod
WHERE prod->>'name' IS NOT NULL
  AND prod->>'name' != ''
  AND m.needs_review = FALSE

UNION ALL

-- FDA drug label brand names
SELECT
    m.id AS molecule_id,
    dl.brand_name AS alias_name,
    LOWER(REGEXP_REPLACE(dl.brand_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'brand' AS alias_type,
    'openfda' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.id = dl.molecule_id
WHERE dl.brand_name IS NOT NULL
  AND dl.brand_name != ''
  AND m.needs_review = FALSE

UNION ALL

-- FDA drug label generic names
SELECT
    m.id AS molecule_id,
    dl.generic_name AS alias_name,
    LOWER(REGEXP_REPLACE(dl.generic_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'generic' AS alias_type,
    'openfda' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.id = dl.molecule_id
WHERE dl.generic_name IS NOT NULL
  AND dl.generic_name != ''
  AND m.needs_review = FALSE

UNION ALL

-- PubChem synonyms
SELECT
    m.id AS molecule_id,
    syn AS alias_name,
    LOWER(REGEXP_REPLACE(syn, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'synonym' AS alias_type,
    'pubchem' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN bronze.pubchem p ON m.inchi_key = p.inchi_key
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(p.synonyms, '[]'::jsonb)) AS syn
WHERE syn IS NOT NULL
  AND syn != ''
  AND m.needs_review = FALSE

UNION ALL

-- Clinical trial intervention names
SELECT DISTINCT
    m.id AS molecule_id,
    ct.intervention_name AS alias_name,
    LOWER(REGEXP_REPLACE(ct.intervention_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'trial_intervention' AS alias_type,
    'clinicaltrials' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.clinical_trials ct ON m.id = ct.molecule_id
WHERE ct.intervention_name IS NOT NULL
  AND ct.intervention_name != ''
  AND m.needs_review = FALSE

UNION ALL

-- Orange Book trade names
SELECT DISTINCT
    m.id AS molecule_id,
    ob.trade_name AS alias_name,
    LOWER(REGEXP_REPLACE(ob.trade_name, '[^a-zA-Z0-9]', '', 'g')) AS alias_name_normalized,
    'trade' AS alias_type,
    'orangebook' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.molecule_aliases ma ON m.id = ma.molecule_id
JOIN bronze.orange_book ob ON LOWER(ma.alias_name) = LOWER(ob.ingredient)
WHERE ob.trade_name IS NOT NULL
  AND ob.trade_name != ''
  AND m.needs_review = FALSE

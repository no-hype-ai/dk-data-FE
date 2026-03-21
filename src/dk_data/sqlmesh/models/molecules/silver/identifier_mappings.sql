-- SQLMesh Model: Silver Identifier Mappings
-- Cross-source identifier mapping table for entity resolution
-- Maps molecule_id to various external identifiers
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_silver.identifier_mappings,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, identifier_type, identifier_value)
    ),
    cron '@daily',
    grain (molecule_id, identifier_type, identifier_value),
    audits (
        not_null(columns := (molecule_id)),
        not_null(columns := (identifier_type)),
        not_null(columns := (identifier_value))
    )
);

-- Collect identifiers from all bronze sources

-- ChEMBL identifiers
SELECT
    m.id AS molecule_id,
    'chembl_id' AS identifier_type,
    c.chembl_id AS identifier_value,
    'chembl' AS source,
    1.0 AS confidence,
    TRUE AS is_primary,
    c.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.chembl_molecules c ON m.inchi_key = c.inchi_key
WHERE c.chembl_id IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- DrugBank identifiers
SELECT
    m.id AS molecule_id,
    'drugbank_id' AS identifier_type,
    d.drugbank_id AS identifier_value,
    'drugbank' AS source,
    1.0 AS confidence,
    TRUE AS is_primary,
    d.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.drugbank d ON m.inchi_key = d.inchi_key
WHERE d.drugbank_id IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- PubChem CIDs
SELECT
    m.id AS molecule_id,
    'pubchem_cid' AS identifier_type,
    p.cid::TEXT AS identifier_value,
    'pubchem' AS source,
    1.0 AS confidence,
    TRUE AS is_primary,
    p.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.pubchem p ON m.inchi_key = p.inchi_key
WHERE p.cid IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- CAS numbers from DrugBank
SELECT
    m.id AS molecule_id,
    'cas_number' AS identifier_type,
    d.cas_number AS identifier_value,
    'drugbank' AS source,
    1.0 AS confidence,
    TRUE AS is_primary,
    d.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.drugbank d ON m.inchi_key = d.inchi_key
WHERE d.cas_number IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- UNII from DrugBank
SELECT
    m.id AS molecule_id,
    'unii' AS identifier_type,
    d.unii AS identifier_value,
    'drugbank' AS source,
    1.0 AS confidence,
    TRUE AS is_primary,
    d.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.drugbank d ON m.inchi_key = d.inchi_key
WHERE d.unii IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- UniProt IDs from targets
SELECT DISTINCT
    m.id AS molecule_id,
    'uniprot_id' AS identifier_type,
    t.target_accession AS identifier_value,
    'chembl' AS source,
    0.9 AS confidence,
    FALSE AS is_primary,
    t.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.molecule_targets mt ON m.id = mt.molecule_id
JOIN mol_silver.targets t ON mt.target_id = t.id
WHERE t.target_accession IS NOT NULL
  AND t.target_accession LIKE '%UniProt%'
  AND m.needs_review = FALSE

UNION ALL

-- RxNorm CUI from drug labels
SELECT DISTINCT
    m.id AS molecule_id,
    'rxcui' AS identifier_type,
    dl.rxcui AS identifier_value,
    'openfda' AS source,
    0.95 AS confidence,
    TRUE AS is_primary,
    dl.effective_date AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.id = dl.molecule_id
WHERE dl.rxcui IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- NDC codes from drug labels
SELECT DISTINCT
    m.id AS molecule_id,
    'ndc' AS identifier_type,
    ndc_code AS identifier_value,
    'openfda' AS source,
    0.9 AS confidence,
    FALSE AS is_primary,
    dl.effective_date AS source_date,
    NOW() AS created_at
FROM mol_silver.drug_labels dl
JOIN mol_silver.molecules m ON m.id = dl.molecule_id
CROSS JOIN LATERAL jsonb_array_elements_text(dl.ndc_codes) AS ndc_code
WHERE dl.ndc_codes IS NOT NULL
  AND jsonb_array_length(dl.ndc_codes) > 0
  AND m.needs_review = FALSE

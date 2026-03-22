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
    m.molecule_id,
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
    m.molecule_id,
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
    m.molecule_id,
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
    m.molecule_id,
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
    m.molecule_id,
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

-- RxCUI from drug labels (stored as JSONB array in bronze)
SELECT DISTINCT
    m.molecule_id,
    'rxcui' AS identifier_type,
    rxcui_val AS identifier_value,
    'openfda' AS source,
    0.95 AS confidence,
    TRUE AS is_primary,
    dl.effective_date AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.molecule_id = dl.molecule_id
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(dl.rxcui, '[]'::jsonb)) AS rxcui_val
WHERE rxcui_val IS NOT NULL
  AND rxcui_val != ''
  AND m.needs_review = FALSE

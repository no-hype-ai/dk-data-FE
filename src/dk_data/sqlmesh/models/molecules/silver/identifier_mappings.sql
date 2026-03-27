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
-- NOTE: mol_bronze.drugbank.inchi_key is NULL (the XML fetcher does not extract
-- structural identifiers). Link via canonical name match using LOWER() normalization.
-- Confidence = 0.85 (name match is less certain than structure match).
SELECT
    m.id AS molecule_id,
    'drugbank_id' AS identifier_type,
    d.drugbank_id AS identifier_value,
    'drugbank' AS source,
    0.85 AS confidence,
    TRUE AS is_primary,
    d.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.drugbank d ON LOWER(m.canonical_name) = LOWER(d.name)
WHERE d.drugbank_id IS NOT NULL
  AND d.name IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- PubChem CIDs
-- mol_bronze.pubchem.inchi_key is populated from the PUG REST API (inchikey field)
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
  AND p.inchi_key IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- CAS numbers from DrugBank (name-based join, same as drugbank_id above)
SELECT
    m.id AS molecule_id,
    'cas_number' AS identifier_type,
    d.cas_number AS identifier_value,
    'drugbank' AS source,
    0.85 AS confidence,
    TRUE AS is_primary,
    d.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.drugbank d ON LOWER(m.canonical_name) = LOWER(d.name)
WHERE d.cas_number IS NOT NULL
  AND d.name IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- UNII from DrugBank
-- NOTE: mol_bronze.drugbank.unii is NULL (the XML fetcher does not extract UNII).
-- This section is intentionally a no-op; kept as a placeholder for when
-- the fetcher is extended to parse UNII from the XML.
SELECT
    m.id AS molecule_id,
    'unii' AS identifier_type,
    d.unii AS identifier_value,
    'drugbank' AS source,
    0.85 AS confidence,
    TRUE AS is_primary,
    d.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.drugbank d ON LOWER(m.canonical_name) = LOWER(d.name)
WHERE d.unii IS NOT NULL
  AND d.name IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- UniProt IDs from targets
-- NOTE: mol_silver.targets uses 'uniprot_id' as the accession column (not 'target_accession')
SELECT DISTINCT
    m.id AS molecule_id,
    'uniprot_id' AS identifier_type,
    t.uniprot_id AS identifier_value,
    'chembl' AS source,
    0.9 AS confidence,
    FALSE AS is_primary,
    t.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.molecule_targets mt ON m.id = mt.molecule_id
JOIN mol_silver.targets t ON mt.target_id = t.id
WHERE t.uniprot_id IS NOT NULL
  AND m.needs_review = FALSE

UNION ALL

-- RxNorm CUI from drug labels
-- NOTE: mol_silver.drug_labels.rxcui is JSONB (array from OpenFDA openfda.rxcui field).
-- Unnest the JSONB array and cast each element to TEXT.
SELECT DISTINCT
    m.id AS molecule_id,
    'rxcui' AS identifier_type,
    rxcui_val::TEXT AS identifier_value,
    'openfda' AS source,
    0.95 AS confidence,
    TRUE AS is_primary,
    dl.effective_date AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.id = dl.molecule_id
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(dl.rxcui, '[]'::JSONB)) AS rxcui_val
WHERE dl.rxcui IS NOT NULL
  AND jsonb_array_length(dl.rxcui) > 0
  AND m.needs_review = FALSE

UNION ALL

-- NDC codes from drug labels
-- NOTE: mol_silver.drug_labels does not have an ndc_codes column (OpenFDA labels
-- do not include NDC codes in the /drug/label endpoint; NDC data comes from
-- the /drug/ndc endpoint which is not currently ingested).
-- This section is intentionally empty — kept as a placeholder.
SELECT DISTINCT
    m.id AS molecule_id,
    'ndc' AS identifier_type,
    ndc_code::TEXT AS identifier_value,
    'openfda' AS source,
    0.9 AS confidence,
    FALSE AS is_primary,
    dl.effective_date AS source_date,
    NOW() AS created_at
FROM mol_silver.drug_labels dl
JOIN mol_silver.molecules m ON m.id = dl.molecule_id
CROSS JOIN LATERAL jsonb_array_elements_text(
    -- application_numbers is the closest available field in mol_silver.drug_labels;
    -- actual NDC codes are not available without a separate NDC ingest pipeline.
    -- Return empty array so this branch produces no rows until NDC is ingested.
    '[]'::JSONB
) AS ndc_code
WHERE FALSE  -- Disabled: ndc_codes column does not exist in mol_silver.drug_labels

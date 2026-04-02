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

-- Collect identifiers from all bronze sources, then deduplicate on the unique key.
-- INCREMENTAL_BY_UNIQUE_KEY uses MERGE; a MERGE fails (CardinalityViolation) if the source
-- batch produces duplicate (molecule_id, identifier_type, identifier_value) rows.
-- The WITH + DISTINCT ON below ensures exactly one row per unique key.
WITH all_ids AS (

-- ChEMBL identifiers
-- Join handles both structural (inchi_key match) and biologic (name match, inchi_key IS NULL)
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
JOIN mol_bronze.chembl_molecules c ON (
    (m.inchi_key IS NOT NULL AND m.inchi_key = c.inchi_key)
    OR (m.inchi_key IS NULL AND LOWER(m.canonical_name) = LOWER(c.pref_name))
)
WHERE c.chembl_id IS NOT NULL

UNION ALL

-- DrugBank identifiers
-- NOTE: mol_bronze.drugbank.inchi_key is NULL (the XML fetcher does not extract
-- structural identifiers). Link via canonical name match using LOWER() normalization.
-- Confidence = 0.85 (name match is less certain than structure match).
-- needs_review filter intentionally omitted: a DrugBank entry's own drugbank_id is
-- authoritative regardless of molecule entity review status.
SELECT
    m.molecule_id,
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

UNION ALL

-- PubChem CIDs
-- mol_bronze.pubchem.inchi_key is populated from the PUG REST API (inchikey field)
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
  AND p.inchi_key IS NOT NULL

UNION ALL

-- CAS numbers from DrugBank (name-based join, same as drugbank_id above)
SELECT
    m.molecule_id,
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

UNION ALL

-- UNII from DrugBank (mol_bronze.drugbank — unii extracted directly from <unii> XML element)
SELECT
    m.molecule_id,
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

UNION ALL

-- UniProt IDs from targets
-- NOTE: mol_silver.targets uses 'uniprot_id' as the accession column (not 'target_accession')
SELECT DISTINCT
    m.molecule_id,
    'uniprot_id' AS identifier_type,
    t.uniprot_id AS identifier_value,
    'chembl' AS source,
    0.9 AS confidence,
    FALSE AS is_primary,
    t.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.molecule_targets mt ON m.molecule_id = mt.molecule_id
JOIN mol_silver.targets t ON mt.target_id = t.id
WHERE t.uniprot_id IS NOT NULL

UNION ALL

-- RxNorm CUI from drug labels
-- NOTE: mol_silver.drug_labels.rxcui is JSONB (array from OpenFDA openfda.rxcui field).
-- Unnest the JSONB array and cast each element to TEXT.
SELECT DISTINCT
    m.molecule_id,
    'rxcui' AS identifier_type,
    rxcui_val::TEXT AS identifier_value,
    'openfda' AS source,
    0.95 AS confidence,
    TRUE AS is_primary,
    dl.effective_date AS source_date,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.molecule_id = dl.molecule_id
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(dl.rxcui, '[]'::JSONB)) AS rxcui_val
WHERE dl.rxcui IS NOT NULL
  AND jsonb_array_length(dl.rxcui) > 0

UNION ALL

-- NDC codes from FDA NDC directory (mol_bronze.fda_ndc)
-- OpenFDA /drug/ndc endpoint: product_ndc mapped to molecule via generic_name alias match.
-- package_ndcs (TEXT[]) contains the full set of 11-digit package-level NDCs per product.
SELECT DISTINCT
    m.molecule_id,
    'ndc' AS identifier_type,
    pkg_ndc::TEXT AS identifier_value,
    'fda_ndc' AS source,
    0.9 AS confidence,
    FALSE AS is_primary,
    n.source_updated_at AS source_date,
    NOW() AS created_at
FROM mol_bronze.fda_ndc n
JOIN mol_silver.molecules m
    ON LOWER(REGEXP_REPLACE(n.generic_name, '[^a-zA-Z0-9]', '', 'g'))
     = LOWER(REGEXP_REPLACE(m.canonical_name, '[^a-zA-Z0-9]', '', 'g'))
CROSS JOIN LATERAL unnest(COALESCE(n.package_ndcs, ARRAY[n.product_ndc])) AS pkg_ndc
WHERE n.generic_name IS NOT NULL
  AND m.molecule_id IS NOT NULL
  AND pkg_ndc IS NOT NULL

)  -- end all_ids CTE

SELECT DISTINCT ON (molecule_id, identifier_type, identifier_value)
    molecule_id,
    identifier_type,
    identifier_value,
    source,
    confidence,
    is_primary,
    source_date,
    NOW() AS created_at
FROM all_ids
WHERE molecule_id IS NOT NULL
  AND identifier_type IS NOT NULL
  AND identifier_value IS NOT NULL
ORDER BY molecule_id, identifier_type, identifier_value, confidence DESC NULLS LAST;

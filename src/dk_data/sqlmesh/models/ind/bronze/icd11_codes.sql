-- SQLMesh Model: Bronze ICD-11 Codes (Indication Domain)
-- Cross-domain bronze model: promotes WHO ICD-11 disease codes from mol_bronze.who_icd
-- to the ind domain. Provides the indication domain's authoritative source of
-- versioned, API-fetched disease classifications.
--
-- Source: mol_bronze.who_icd (WHO ICD-11 API, fetched by WHOICDFetcher via mol_raw.who_icd)
-- Grain: icd11_code
-- Usage: ind_silver.icd11_ontology reads from this table.
--
-- Note: Cross-domain bronze→bronze reference is intentional. The WHO ICD fetcher
-- and its raw table live in the mol domain (mol_raw.who_icd / mol_bronze.who_icd)
-- since it was originally built for drug/molecule disease linkage. The ind domain
-- creates its own view here to decouple scheduling and enable ind-specific audits.
--
-- Feature: 019-cms-puf-platform-reconciliation (indication bronze layer)

MODEL (
    name ind_bronze.icd11_codes,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (icd11_code, title)),
        unique_values(columns := (icd11_code))
    ),
    grain icd11_code
);

SELECT
    gen_random_uuid()                   AS id,
    b.icd_code                          AS icd11_code,
    b.title,
    b.class_kind,
    b.definition,
    b.browser_url,

    -- Derive parent code from ICD-11 stem code pattern (e.g. "2A00.10" -> "2A00")
    CASE
        WHEN b.icd_code LIKE '%.%' THEN split_part(b.icd_code, '.', 1)
        ELSE NULL
    END                                 AS parent_code,

    -- Leaf codes have sub-decimal specificity
    CASE
        WHEN b.icd_code LIKE '%.%'     THEN TRUE
        WHEN b.class_kind = 'category' THEN TRUE
        ELSE FALSE
    END                                 AS is_leaf,

    -- Parent/child hierarchy URIs as JSONB
    b.parent_uris,
    b.child_uris,

    -- Inclusion/exclusion term arrays
    b.inclusion_terms,
    b.exclusion_terms,
    b.exclusion_terms2,

    b.source,
    b.source_updated_at,
    NOW()                               AS created_at

FROM mol_bronze.who_icd b
WHERE b.icd_code IS NOT NULL
  AND b.title IS NOT NULL;

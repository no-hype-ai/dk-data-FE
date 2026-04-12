-- SQLMesh Model: hcs_silver.cms_ddinter
-- Drug-drug interaction data with molecule linkage via molecule_names hub.
--
-- ⚠️ NOTE (020-drugbank-seed-schema-fix): The DDInter source (ddinter.scbdd.com)
-- has been permanently unreachable since March 2026. The bronze source is retired.
-- Drug-drug interaction data is fully covered by mol_bronze.drugbank → mol_silver.drug_pharmacology.
-- This model is retained for any historical raw data ingested before the outage.
--
-- Source: hcs_bronze.cms_ddinter (columns: drug_a, drug_b, interaction_type, severity, description)
-- Molecule linkage:
--   drug_a → mol_silver.molecule_names (normalized_name equi-join, LATERAL LIMIT 1)
--   drug_b → mol_silver.molecule_names (normalized_name equi-join, LATERAL LIMIT 1)
--
-- Grain: (drug_a, drug_b)
--
-- Feature: 001-silver-medallion-rebuild

MODEL (
    name hcs_silver.cms_ddinter,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (drug_a, drug_b)
    ),
    cron '@yearly',
    audits (
        not_null(columns := (drug_a, drug_b))
    ),
    grain (drug_a, drug_b),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.drug_a, b.drug_b)
    gen_random_uuid()               AS id,
    b.drug_a,
    b.drug_b,
    b.interaction_type,
    b.severity,
    b.description,

    -- Molecule linkage for drug_a
    mol_a.molecule_id               AS molecule_id_a,
    -- Molecule linkage for drug_b
    mol_b.molecule_id               AS molecule_id_b,

    b.source,
    b.ingested_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_ddinter b

-- drug_a → molecule_names (normalized_name equi-join, LIMIT 1 prevents fan-out)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE b.drug_a IS NOT NULL
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(b.drug_a, '[^a-zA-Z0-9]', '', 'g'))
    ORDER BY mn.molecule_id
    LIMIT 1
) mol_a ON TRUE

-- drug_b → molecule_names (normalized_name equi-join, LIMIT 1 prevents fan-out)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE b.drug_b IS NOT NULL
      AND mn.normalized_name = LOWER(REGEXP_REPLACE(b.drug_b, '[^a-zA-Z0-9]', '', 'g'))
    ORDER BY mn.molecule_id
    LIMIT 1
) mol_b ON TRUE

WHERE b.drug_a IS NOT NULL
  AND b.drug_b IS NOT NULL
ORDER BY b.drug_a, b.drug_b, b.ingested_at DESC;

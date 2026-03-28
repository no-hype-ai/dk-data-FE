-- SQLMesh Model: Silver Molecule Targets
-- Junction table linking molecules to their biological targets
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_silver.molecule_targets,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, target_id)
    ),
    cron '@daily',
    grain (molecule_id, target_id),
    audits (
        not_null(columns := (molecule_id)),
        not_null(columns := (target_id))
    )
);

-- Extract molecule-target relationships from bioactivity data
SELECT DISTINCT
    b.molecule_id,
    t.id AS target_id,
    b.assay_type,
    b.activity_type,
    b.activity_value,
    b.activity_unit,
    CASE
        WHEN b.activity_type = 'IC50' AND b.activity_value < 100 THEN 'potent'
        WHEN b.activity_type = 'IC50' AND b.activity_value < 1000 THEN 'moderate'
        WHEN b.activity_type = 'Ki' AND b.activity_value < 10 THEN 'potent'
        WHEN b.activity_type = 'Ki' AND b.activity_value < 100 THEN 'moderate'
        WHEN b.activity_type = 'EC50' AND b.activity_value < 100 THEN 'potent'
        ELSE 'weak'
    END AS potency_class,
    b.source,
    b.created_at

FROM mol_silver.bioactivity b
JOIN mol_silver.targets t ON b.target_id = t.id
JOIN mol_silver.molecules m ON b.molecule_id = m.molecule_id
WHERE b.molecule_id IS NOT NULL
  AND b.target_id IS NOT NULL

UNION ALL

-- Add target relationships from DrugBank
-- NOTE: mol_bronze.drugbank.inchi_key is NULL (the DrugBank XML fetcher does not
-- extract structural identifiers). Join via name match directly to avoid a
-- circular dependency with identifier_mappings (which itself joins molecule_targets).
SELECT DISTINCT
    m.molecule_id,
    t.id AS target_id,
    'pharmacology' AS assay_type,
    'target' AS activity_type,
    NULL::NUMERIC AS activity_value,
    NULL::TEXT AS activity_unit,
    'unknown' AS potency_class,
    'drugbank' AS source,
    NOW() AS created_at
FROM mol_silver.molecules m
JOIN mol_bronze.drugbank d ON LOWER(m.canonical_name) = LOWER(d.name)
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(d.targets, '[]'::JSONB)) AS tgt
JOIN mol_silver.targets t ON strpos(LOWER(t.target_name), LOWER(tgt->>'name')) > 0
WHERE tgt->>'name' IS NOT NULL
  AND d.name IS NOT NULL

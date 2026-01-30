-- SQLMesh Model: Silver Molecule Targets
-- Junction table linking molecules to their biological targets
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name silver.molecule_targets,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, target_id)
    ),
    cron '@daily',
    grain (molecule_id, target_id),
    audits (
        not_null(molecule_id),
        not_null(target_id)
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

FROM silver.bioactivity b
JOIN silver.targets t ON b.target_id = t.id
JOIN silver.molecules m ON b.molecule_id = m.id
WHERE m.needs_review = FALSE
  AND b.molecule_id IS NOT NULL
  AND b.target_id IS NOT NULL

UNION ALL

-- Add target relationships from DrugBank
SELECT DISTINCT
    m.id AS molecule_id,
    t.id AS target_id,
    'pharmacology' AS assay_type,
    'target' AS activity_type,
    NULL::NUMERIC AS activity_value,
    NULL AS activity_unit,
    'unknown' AS potency_class,
    'drugbank' AS source,
    NOW() AS created_at
FROM silver.molecules m
JOIN bronze.drugbank d ON m.inchi_key = d.inchi_key
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(d.targets, '[]'::jsonb)) AS tgt
JOIN silver.targets t ON t.target_name ILIKE '%' || (tgt->>'name') || '%'
WHERE m.needs_review = FALSE
  AND tgt->>'name' IS NOT NULL

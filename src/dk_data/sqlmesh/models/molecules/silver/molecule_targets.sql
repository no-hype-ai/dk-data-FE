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

-- ChEMBL bioactivity-based molecule-target relationships
WITH chembl_sources AS (
    SELECT DISTINCT
        b.molecule_id,
        t.id AS target_id,
        b.assay_type,
        b.standard_type AS activity_type,
        b.standard_value AS activity_value,
        b.standard_units AS activity_unit,
        CASE
            WHEN b.standard_type = 'IC50' AND b.standard_value < 100 THEN 'potent'
            WHEN b.standard_type = 'IC50' AND b.standard_value < 1000 THEN 'moderate'
            WHEN b.standard_type = 'Ki' AND b.standard_value < 10 THEN 'potent'
            WHEN b.standard_type = 'Ki' AND b.standard_value < 100 THEN 'moderate'
            WHEN b.standard_type = 'EC50' AND b.standard_value < 100 THEN 'potent'
            ELSE 'weak'
        END AS potency_class,
        b.source,
        b.created_at
    FROM mol_silver.bioactivity b
    JOIN mol_silver.targets t ON EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(t.cross_references, '[]'::jsonb)) AS ref
        WHERE ref->>'database' = 'ChEMBL' AND ref->>'id' = b.target_chembl_id
    )
    JOIN mol_silver.molecules m ON b.molecule_id = m.molecule_id
    WHERE m.needs_review = FALSE
      AND b.molecule_id IS NOT NULL
      AND b.target_chembl_id IS NOT NULL
),

-- DrugBank molecule-target relationships via JSONB targets array.
-- LATERAL expansion is isolated in this CTE so the derived column
-- target_protein_name can be used in a plain JOIN ON (no LATERAL in ON clause).
drugbank_expanded AS (
    SELECT
        m.molecule_id,
        tgt->>'name' AS target_protein_name
    FROM mol_silver.molecules m
    JOIN mol_bronze.drugbank db ON m.inchi_key = db.inchi_key
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(db.targets, '[]'::jsonb)) AS tgt
    WHERE m.needs_review = FALSE
      AND m.molecule_id IS NOT NULL
      AND tgt->>'name' IS NOT NULL
),

drugbank_sources AS (
    SELECT DISTINCT
        de.molecule_id,
        t.id AS target_id,
        NULL AS assay_type,
        NULL AS activity_type,
        NULL::NUMERIC AS activity_value,
        NULL AS activity_unit,
        'unknown' AS potency_class,
        'drugbank' AS source,
        NOW() AS created_at
    FROM drugbank_expanded de
    JOIN mol_silver.targets t ON t.protein_name ILIKE '%' || de.target_protein_name || '%'
    WHERE t.id IS NOT NULL
)

SELECT molecule_id, target_id, assay_type, activity_type, activity_value, activity_unit, potency_class, source, created_at
FROM chembl_sources
UNION ALL
SELECT molecule_id, target_id, assay_type, activity_type, activity_value, activity_unit, potency_class, source, created_at
FROM drugbank_sources


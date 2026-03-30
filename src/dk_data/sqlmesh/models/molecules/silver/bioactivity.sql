-- SQLMesh Model: Silver Bioactivity
-- Normalized bioactivity data from ChEMBL activity assay measurements.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Source: mol_bronze.chembl_activities (ChEMBL /api/data/activity endpoint)
-- Entity linking:
--   molecule_id: chembl_id → mol_silver.molecules via identifier_mappings (chembl_id type)
--               OR inchi_key → mol_silver.molecules via canonical structures
--   target_id:  target_chembl_id → mol_silver.targets (target lookup via chembl target id)

MODEL (
    name mol_silver.bioactivity,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column source_updated_at,
        batch_size 1000
    ),
    cron '@weekly',
    audits (
        not_null(columns := (activity_id, chembl_id))
    ),
    grain activity_id
);

SELECT
    gen_random_uuid()                                               AS id,
    b.chembl_id,

    -- molecule_id: resolve directly via mol_bronze.chembl_molecules + mol_silver.molecules.
    -- Do NOT use mol_silver.identifier_mappings here — identifier_mappings depends on
    -- mol_silver.molecule_targets, which depends on mol_silver.bioactivity, creating a cycle.
    (
        SELECT m.molecule_id
        FROM mol_bronze.chembl_molecules c
        JOIN mol_silver.molecules m ON (
            (m.inchi_key IS NOT NULL AND m.inchi_key = c.inchi_key)
            OR (m.inchi_key IS NULL AND LOWER(m.canonical_name) = LOWER(c.pref_name))
        )
        WHERE c.chembl_id = b.chembl_id
        LIMIT 1
    )                                                               AS molecule_id,

    -- target_id: resolve via mol_silver.targets (chembl_target_id lookup)
    (
        SELECT t.id
        FROM mol_silver.targets t
        WHERE t.chembl_target_id = b.target_chembl_id
        LIMIT 1
    )                                                               AS target_id,

    b.activity_id,
    b.assay_chembl_id,
    b.assay_type,
    b.assay_description,
    b.target_chembl_id,
    b.target_pref_name                                              AS target_name,
    b.target_type,
    b.target_organism,

    -- Activity measurements
    b.activity_type,
    b.activity_value,
    b.activity_unit,
    b.standard_relation,
    b.pchembl_value,

    -- Activity flags
    b.activity_comment,
    b.data_validity_comment,
    b.potential_duplicate,

    -- Document reference
    b.document_chembl_id,
    NULL::BIGINT                                                    AS pubmed_id,
    b.publication_year,

    b.source,
    b.source_updated_at,
    NOW()                                                           AS created_at

FROM mol_bronze.chembl_activities b
WHERE b.activity_id IS NOT NULL
  AND b.chembl_id IS NOT NULL
  AND b.source_updated_at BETWEEN @start_dt AND @end_dt;

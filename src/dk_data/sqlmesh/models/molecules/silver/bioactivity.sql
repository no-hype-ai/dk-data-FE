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

    -- molecule_id: resolve via identifier_mappings (chembl_id → molecule_id)
    -- Falls back to NULL if no match (molecule not yet in registry)
    (
        SELECT im.molecule_id
        FROM mol_silver.identifier_mappings im
        WHERE im.identifier_type = 'chembl_id'
          AND im.identifier_value = b.chembl_id
        LIMIT 1
    )                                                               AS molecule_id,

    -- target_id: resolve via mol_silver.targets (target_chembl_id lookup)
    (
        SELECT t.id
        FROM mol_silver.targets t
        WHERE t.chembl_id = b.target_chembl_id
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

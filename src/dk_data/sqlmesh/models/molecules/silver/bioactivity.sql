-- SQLMesh Model: Silver Bioactivity
-- Binding affinity and bioactivity data from BindingDB (primary) + ChEMBL (future).
-- Deduplicated by activity_id (bindingdb_id-based). Linked to mol_silver.molecules
-- via inchi_key join. Null-padded columns ensure schema stability as sources are added.
-- Part of: 012-dk-data-platform

MODEL (
    name mol_silver.bioactivity,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key activity_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (activity_id))
    ),
    grain activity_id
);

-- BindingDB as primary binding affinity source
WITH bindingdb_data AS (
    SELECT
        'bindingdb:' || b.bindingdb_id                  AS activity_id,
        m.molecule_id,
        b.inchi_key,

        -- ChEMBL-compatible fields (NULL where BindingDB doesn't provide)
        NULL::TEXT                                      AS chembl_id,
        NULL::TEXT                                      AS assay_chembl_id,
        CASE
            WHEN b.activity_type IS NOT NULL THEN b.activity_type
            WHEN b.ki_nm IS NOT NULL         THEN 'Ki'
            WHEN b.ic50_nm IS NOT NULL       THEN 'IC50'
            WHEN b.kd_nm IS NOT NULL         THEN 'Kd'
            WHEN b.ec50_nm IS NOT NULL       THEN 'EC50'
            ELSE NULL
        END                                             AS assay_type,
        NULL::TEXT                                      AS assay_description,
        NULL::TEXT                                      AS target_chembl_id,
        b.target_name,
        NULL::TEXT                                      AS target_type,
        b.target_organism,
        b.target_source_id                              AS uniprot_id,

        -- Activity measurements — normalise to standard_type/value/units
        COALESCE(b.activity_type,
            CASE
                WHEN b.ki_nm   IS NOT NULL THEN 'Ki'
                WHEN b.ic50_nm IS NOT NULL THEN 'IC50'
                WHEN b.kd_nm   IS NOT NULL THEN 'Kd'
                WHEN b.ec50_nm IS NOT NULL THEN 'EC50'
                ELSE 'Activity'
            END
        )                                               AS standard_type,
        COALESCE(
            b.activity_value,
            b.ki_nm, b.ic50_nm, b.kd_nm, b.ec50_nm
        )                                               AS standard_value,
        COALESCE(b.activity_unit, 'nM')                 AS standard_units,
        NULL::TEXT                                      AS standard_relation,

        -- pChEMBL = -log10(value_M); convert nM → M first
        CASE
            WHEN COALESCE(b.activity_value, b.ki_nm, b.ic50_nm, b.kd_nm, b.ec50_nm) > 0
                THEN ROUND(
                    (-LOG(COALESCE(b.activity_value, b.ki_nm, b.ic50_nm, b.kd_nm, b.ec50_nm) / 1e9))::NUMERIC,
                    2
                )
            ELSE NULL
        END                                             AS pchembl_value,

        NULL::TEXT                                      AS activity_comment,
        NULL::TEXT                                      AS data_validity_comment,
        NULL::BOOLEAN                                   AS potential_duplicate,

        b.doi                                           AS document_chembl_id,
        b.pmid                                          AS pubmed_id,
        NULL::INTEGER                                   AS publication_year,

        'bindingdb'                                     AS source,
        b.source_updated_at,
        b.ingested_at                                   AS created_at

    FROM mol_bronze.bindingdb b
    LEFT JOIN mol_silver.molecules m ON b.inchi_key = m.inchi_key
    WHERE b.processed_to_silver = FALSE
      AND b.bindingdb_id IS NOT NULL
)

SELECT
    gen_random_uuid()   AS id,
    activity_id,
    molecule_id,
    inchi_key,
    chembl_id,
    assay_chembl_id,
    assay_type,
    assay_description,
    target_chembl_id,
    target_name,
    target_type,
    target_organism,
    uniprot_id,
    standard_type,
    standard_value,
    standard_units,
    standard_relation,
    pchembl_value,
    activity_comment,
    data_validity_comment,
    potential_duplicate,
    document_chembl_id,
    pubmed_id,
    publication_year,
    source,
    source_updated_at,
    created_at

FROM bindingdb_data

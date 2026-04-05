-- SQLMesh Model: Bronze ChEMBL Activities
-- Unnests activity records from mol_raw.chembl_activities page blobs.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- ChEMBL activity API field names (v1):
--   activity_id, assay_chembl_id, assay_type, assay_description,
--   target_chembl_id, target_pref_name, target_type, target_organism,
--   molecule_chembl_id, pref_name, canonical_smiles,
--   standard_type (IC50/Ki/EC50/...), standard_value, standard_units,
--   standard_relation, pchembl_value, activity_comment, data_validity_comment,
--   potential_duplicate, document_chembl_id, document_journal, document_year

MODEL (
    name mol_bronze.chembl_activities,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@weekly',
    audits (
        not_null(columns := (activity_id, chembl_id))
    ),
    grain activity_id
);

WITH activities AS (
    SELECT
        raw.id              AS raw_source_id,
        raw.ingested_at,
        act.value           AS act
    FROM mol_raw.chembl_activities AS raw
    CROSS JOIN LATERAL jsonb_array_elements(
        COALESCE(raw.response_body->'activities', '[]'::JSONB)
    ) AS act(value)
    WHERE raw.response_status = 200
      AND raw.ingested_at BETWEEN @start_dt AND @end_dt
),

deduped AS (
    SELECT DISTINCT ON (act->>'activity_id')
        raw_source_id,
        ingested_at,
        act
    FROM activities
    WHERE act->>'activity_id' IS NOT NULL
    ORDER BY act->>'activity_id', ingested_at DESC
)

SELECT
    gen_random_uuid()                                               AS id,

    -- Activity identifier
    act->>'activity_id'                                             AS activity_id,

    -- Molecule identifiers
    act->>'molecule_chembl_id'                                      AS chembl_id,
    act->>'canonical_smiles'                                        AS canonical_smiles,

    -- Assay context
    act->>'assay_chembl_id'                                         AS assay_chembl_id,
    act->>'assay_type'                                              AS assay_type,
    act->>'assay_description'                                       AS assay_description,

    -- Target context
    act->>'target_chembl_id'                                        AS target_chembl_id,
    act->>'target_pref_name'                                        AS target_pref_name,
    act->>'target_type'                                             AS target_type,
    act->>'target_organism'                                         AS target_organism,

    -- Activity measurement
    act->>'standard_type'                                           AS activity_type,
    (act->>'standard_value')::NUMERIC                               AS activity_value,
    act->>'standard_units'                                          AS activity_unit,
    act->>'standard_relation'                                       AS standard_relation,
    (act->>'pchembl_value')::NUMERIC                                AS pchembl_value,

    -- Quality flags
    act->>'activity_comment'                                        AS activity_comment,
    act->>'data_validity_comment'                                   AS data_validity_comment,
    CASE act->>'potential_duplicate'
        WHEN 'true' THEN TRUE WHEN '1' THEN TRUE
        WHEN 'false' THEN FALSE WHEN '0' THEN FALSE
        ELSE NULL
    END                                                             AS potential_duplicate,

    -- Publication reference
    act->>'document_chembl_id'                                      AS document_chembl_id,
    (act->>'document_year')::INTEGER                                AS publication_year,

    -- Source tracking
    act                                                             AS raw_json,
    raw_source_id,
    'chembl'                                                        AS source,
    ingested_at,
    ingested_at                                                   AS source_updated_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM deduped;

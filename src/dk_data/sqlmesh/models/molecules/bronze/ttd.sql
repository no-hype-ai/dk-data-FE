-- SQLMesh Model: Bronze Therapeutic Target Database (TTD)
-- Transforms raw TTD API responses to Bronze typed columns.
-- API: http://db.idrblab.net/ttd/data/drug/details/{id}  (drug info)
--      http://db.idrblab.net/ttd/data/target/details/{id} (target info)
-- Response shape: {"data": {TTD_ID, "Drug Name", "Drug Type", "Status", "Targets": [...], ...}}
--             or: {"drugid", "drugname", "target": [...], ...}

MODEL (
    name mol_bronze.ttd,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key ttd_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (ttd_id))
    ),
    grain ttd_id
);

-- Normalise both response shapes into a single record
WITH normalised AS (
    SELECT
        r.id              AS raw_source_id,
        r.request_timestamp,
        CASE
            WHEN r.response_body ? 'data' THEN r.response_body->'data'
            ELSE r.response_body
        END AS rec
    FROM mol_raw.ttd r
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body IS NOT NULL
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
)

SELECT DISTINCT ON (
    COALESCE(rec->>'TTD_ID', rec->>'drugid', rec->>'targetid', rec->>'ttd_id')
)
    gen_random_uuid()                                                               AS id,
    COALESCE(rec->>'TTD_ID', rec->>'drugid', rec->>'targetid', rec->>'ttd_id')     AS ttd_id,

    -- Entity type: drug or target
    CASE
        WHEN rec ? 'Drug Name' OR rec ? 'drugname' THEN 'drug'
        WHEN rec ? 'targetid' OR rec ? 'TargetID'  THEN 'target'
        ELSE 'unknown'
    END                                                                             AS entity_type,

    -- Drug fields
    COALESCE(rec->>'Drug Name', rec->>'drugname', rec->>'name')                    AS drug_name,
    COALESCE(rec->>'Drug Type', rec->>'drugtype')                                  AS drug_type,
    COALESCE(rec->>'Highest_clinical_trial_phase', rec->>'status',
             rec->>'Drug_Status')                                                   AS drug_status,
    rec->>'CAS Number'                                                             AS cas_number,
    COALESCE(rec->>'Inchi_Key', rec->>'inchi_key', rec->>'InChIKey')              AS inchi_key,
    rec->>'SMILES'                                                                 AS smiles,
    COALESCE(rec->>'PubChem CID', rec->>'pubchem_cid')                            AS pubchem_cid,

    -- Target fields
    COALESCE(rec->>'Target Name', rec->>'targetname')                              AS target_name,
    COALESCE(rec->>'Target Type', rec->>'targettype')                              AS target_type,
    rec->>'UniProt ID'                                                             AS uniprot_id,

    -- Cross-references
    COALESCE(rec->'Targets', rec->'target')                                        AS targets,
    rec->'drug_class'                                                              AS drug_class,
    rec->'synonyms'                                                                AS synonyms,

    -- Raw source tracking
    rec                                                                            AS raw_json,
    raw_source_id,
    'ttd'                                                                          AS source,
    request_timestamp,
    request_timestamp                                                              AS source_updated_at,
    FALSE                                                                          AS processed_to_silver,
    NOW()                                                                          AS created_at

FROM normalised
WHERE COALESCE(rec->>'TTD_ID', rec->>'drugid', rec->>'targetid', rec->>'ttd_id') IS NOT NULL
ORDER BY
    COALESCE(rec->>'TTD_ID', rec->>'drugid', rec->>'targetid', rec->>'ttd_id'),
    request_timestamp DESC NULLS LAST;

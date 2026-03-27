-- SQLMesh Model: Bronze RxNorm Concepts
-- Transforms raw RxNorm API responses into typed bronze layer.
-- Handles idGroup (rxcui lookup), properties, and relatedGroup response formats.
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.rxnorm,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key rxcui
    ),
    cron '@weekly',
    grain rxcui,
    audits (
        not_null(columns := (rxcui)),
        unique_values(columns := (rxcui))
    )
);

-- idGroup format: {"idGroup": {"rxnormId": ["12345"], "name": "...", "tty": "..."}}
WITH from_id_group AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        r.response_body->'idGroup'->'rxnormId'->>0    AS rxcui,
        r.response_body->'idGroup'->>'name'           AS name,
        r.response_body->'idGroup'->>'tty'            AS tty,
        NULL::TEXT                                    AS synonym,
        NULL::TEXT                                    AS suppress,
        r.response_body                               AS raw_json
    FROM mol_raw.rxnorm r
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body->'idGroup' IS NOT NULL
      AND r.response_body->'idGroup'->>'rxnormId' IS NOT NULL
),

-- properties format: {"properties": {"rxcui": "...", "name": "...", "tty": "...", "synonym": "..."}}
from_properties AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        r.response_body->'properties'->>'rxcui'    AS rxcui,
        r.response_body->'properties'->>'name'     AS name,
        r.response_body->'properties'->>'tty'      AS tty,
        r.response_body->'properties'->>'synonym'  AS synonym,
        r.response_body->'properties'->>'suppress' AS suppress,
        r.response_body                            AS raw_json
    FROM mol_raw.rxnorm r
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body->'properties' IS NOT NULL
      AND r.response_body->'properties'->>'rxcui' IS NOT NULL
),

-- relatedGroup format: {"relatedGroup": {"conceptGroup": [{"conceptProperties": [{...}]}]}}
from_related AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        prop->>'rxcui'    AS rxcui,
        prop->>'name'     AS name,
        prop->>'tty'      AS tty,
        prop->>'synonym'  AS synonym,
        NULL::TEXT        AS suppress,
        r.response_body   AS raw_json
    FROM mol_raw.rxnorm r,
         jsonb_array_elements(r.response_body->'relatedGroup'->'conceptGroup') AS cg,
         jsonb_array_elements(cg->'conceptProperties') AS prop
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body->'relatedGroup' IS NOT NULL
      AND prop->>'rxcui' IS NOT NULL
),

combined AS (
    SELECT * FROM from_id_group
    UNION ALL
    SELECT * FROM from_properties
    UNION ALL
    SELECT * FROM from_related
)

SELECT DISTINCT ON (rxcui)
    gen_random_uuid() AS id,
    raw_id,
    rxcui,
    name,
    tty,
    synonym,
    suppress,
    NULL::JSONB AS ingredients,
    NULL::JSONB AS brand_names,
    NULL::JSONB AS ndc_codes,
    NULL::JSONB AS atc_codes,
    NULL::JSONB AS drug_classes,
    raw_json,
    FALSE       AS processed_to_silver,
    request_timestamp,
    request_timestamp AS ingested_at,
    'rxnorm'    AS source,
    request_timestamp AS source_updated_at

FROM combined
WHERE rxcui IS NOT NULL
ORDER BY rxcui, request_timestamp DESC NULLS LAST

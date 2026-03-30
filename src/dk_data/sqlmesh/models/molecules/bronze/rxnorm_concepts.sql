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

-- Enrichment from "related" strategy fetch responses:
-- /rxcui/{rxcui}/related.json responses store _strategy="related" and _rxcui=<source>.
-- Group by source rxcui to build ingredient/brand_name/atc/drug_class arrays.
related_enrichment AS (
    SELECT
        r.response_body->>'_rxcui'                                          AS source_rxcui,
        jsonb_agg(DISTINCT prop->>'name') FILTER (
            WHERE cg->>'tty' IN ('IN', 'MIN', 'PIN')
        )                                                                    AS ingredients,
        jsonb_agg(DISTINCT prop->>'name') FILTER (
            WHERE cg->>'tty' = 'BN'
        )                                                                    AS brand_names,
        jsonb_agg(DISTINCT prop->>'rxcui') FILTER (
            WHERE cg->>'tty' IN ('ATC', 'VA')
        )                                                                    AS atc_codes,
        jsonb_agg(DISTINCT prop->>'name') FILTER (
            WHERE cg->>'tty' IN ('EPC', 'MoA', 'TC', 'PK', 'PE', 'CS')
        )                                                                    AS drug_classes,
        -- NDC codes: tty='NDC' entries in relatedGroup; name contains the NDC string
        jsonb_agg(DISTINCT prop->>'name') FILTER (
            WHERE cg->>'tty' = 'NDC'
        )                                                                    AS ndc_codes
    FROM mol_raw.rxnorm r,
         jsonb_array_elements(r.response_body->'relatedGroup'->'conceptGroup') AS cg,
         jsonb_array_elements(cg->'conceptProperties') AS prop
    WHERE r.response_status = 200
      AND r.response_body->>'_strategy' = 'related'
      AND r.response_body->>'_rxcui' IS NOT NULL
    GROUP BY r.response_body->>'_rxcui'
),

combined AS (
    SELECT * FROM from_id_group
    UNION ALL
    SELECT * FROM from_properties
    UNION ALL
    SELECT * FROM from_related
)

SELECT DISTINCT ON (c.rxcui)
    gen_random_uuid() AS id,
    c.raw_id,
    c.rxcui,
    c.name,
    c.tty,
    c.synonym,
    c.suppress,
    e.ingredients,
    e.brand_names,
    e.ndc_codes,
    e.atc_codes,
    e.drug_classes,
    c.raw_json,
    FALSE       AS processed_to_silver,
    c.request_timestamp,
    c.request_timestamp AS ingested_at,
    'rxnorm'    AS source,
    c.request_timestamp AS source_updated_at

FROM combined c
LEFT JOIN related_enrichment e ON e.source_rxcui = c.rxcui
WHERE c.rxcui IS NOT NULL
ORDER BY c.rxcui, c.request_timestamp DESC NULLS LAST

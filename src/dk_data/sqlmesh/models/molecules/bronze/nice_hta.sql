-- SQLMesh Model: Bronze NICE HTA Decisions
-- Transforms raw NICE Technology Appraisal API responses to Bronze typed columns.
-- API: https://api.nice.org.uk/services/guidance/published (JSON)
--      https://www.nice.org.uk/search (HTML fallback, stored as response_text)
-- Response shape: {"Data": [{Id, Title, GuidanceType, PublishedDate, LastUpdated}], "Total": N}
-- or individual guidance page: {"id": "...", "title": "...", "decision": "...", ...}

MODEL (
    name mol_bronze.nice_hta,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key guidance_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (guidance_id))
    ),
    grain guidance_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Guidance list responses: {"Data": [...]}
WITH from_list AS (
    SELECT
        r.id              AS raw_source_id,
        r.ingested_at,
        item.value        AS rec,
        'list'            AS response_type
    FROM mol_raw.nice_hta r,
         LATERAL jsonb_array_elements(r.response_body->'Data') AS item(value)
    WHERE r.response_body ? 'Data'
      AND r.ingested_at BETWEEN @start_dt AND @end_dt
),

-- Individual guidance detail responses (flat object at root with id + title)
from_detail AS (
    SELECT
        r.id              AS raw_source_id,
        r.ingested_at,
        r.response_body   AS rec,
        'detail'          AS response_type
    FROM mol_raw.nice_hta r
    WHERE NOT (r.response_body ? 'Data')
      AND (r.response_body ? 'id' OR r.response_body ? 'title')
      AND r.ingested_at BETWEEN @start_dt AND @end_dt
),

combined AS (
    SELECT * FROM from_list
    UNION ALL
    SELECT * FROM from_detail
)

SELECT DISTINCT ON (COALESCE(rec->>'Id', rec->>'id', rec->>'guidance_id'))
    gen_random_uuid()                                                   AS id,

    COALESCE(rec->>'Id', rec->>'id', rec->>'guidance_id')              AS guidance_id,
    COALESCE(rec->>'Title', rec->>'title')                             AS title,
    rec->>'GuidanceType'                                               AS guidance_type,
    rec->>'drug_name'                                                  AS drug_name,

    -- Decision fields (populated from detail responses)
    rec->>'decision'                                                   AS decision,
    rec->>'recommendation'                                             AS recommendation,
    rec->>'icer_value'                                                 AS icer_value,

    -- Dates
    CASE
        WHEN (rec->>'PublishedDate') IS NOT NULL
        THEN (rec->>'PublishedDate')::TIMESTAMPTZ::DATE
        WHEN (rec->>'published_date') IS NOT NULL
        THEN (rec->>'published_date')::TIMESTAMPTZ::DATE
        ELSE NULL
    END                                                                AS published_date,

    CASE
        WHEN (rec->>'LastUpdated') IS NOT NULL
        THEN (rec->>'LastUpdated')::TIMESTAMPTZ::DATE
        ELSE NULL
    END                                                                AS last_updated_date,

    -- Raw source tracking
    rec                                                                AS raw_json,
    raw_source_id,
    'nice_hta'                                                         AS source,
    ingested_at,
    ingested_at                                                    AS source_updated_at,
    FALSE                                                              AS processed_to_silver,
    NOW()                                                              AS created_at

FROM combined
WHERE COALESCE(rec->>'Id', rec->>'id', rec->>'guidance_id') IS NOT NULL
ORDER BY COALESCE(rec->>'Id', rec->>'id', rec->>'guidance_id'), ingested_at DESC NULLS LAST;

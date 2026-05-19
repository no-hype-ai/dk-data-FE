-- SQLMesh Model: Bronze WHO ICD Codes
-- Transforms mol_raw.who_icd JSONB envelope (migration 075_pdb_who_raw_tables.sql)
-- to Bronze typed columns.
--
-- WHO ICD-11 API field reference (verified against 2024-01 MMS linearization):
--   response_body->>'code'                   ICD-11 stem code (e.g. "1C83.0"); empty on block nodes
--   response_body->'title'->>'@value'        Human-readable title (multilingual object)
--   response_body->>'classKind'              'category' | 'block' | 'chapter'
--   response_body->>'browserUrl'             canonical WHO browser URL
--   response_body->'definition'->>'@value'   definition text (chapters/some categories)
--   response_body->'parent'                  JSONB array of parent @id URIs
--   response_body->'child'                   JSONB array of child @id URIs
--   response_body->'inclusion'               JSONB array [{label:{@value,@language}}]
--   response_body->'exclusion'               JSONB array [{label:{@value,@language}}]
--
-- WHO ICD-10 API field reference (verified against 2019 linearization):
--   response_body->>'code'                   ICD-10 code (e.g. "A00.0", "A00-A09", "I")
--   response_body->'title'->>'@value'        SAME @value wrapper as ICD-11 (NOT a flat 'description')
--   response_body->>'classKind'              'chapter' | 'block' | 'category'
--   response_body->>'browserUrl'             canonical WHO browser URL
--   response_body->'parent'                  JSONB array of parent @id URIs
--   response_body->'child'                   JSONB array of child @id URIs
--   response_body->'inclusion'               JSONB array [{label:{@value,@language}}]
--   response_body->'exclusion'               JSONB array [{label:{@value,@language}}]
--   response_body->'codingHint'              JSONB array of coding instructions (some nodes only)
--
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.who_icd,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key id
    ),
    cron '@daily',
    audits (
        not_null(columns := (icd_code))
    ),
    grain (id)
);

SELECT
    gen_random_uuid()                                     AS id,

    -- ICD code — present in both ICD-10 and ICD-11 responses
    response_body->>'code'                                AS icd_code,

    -- Title: both ICD-11 and ICD-10 use {"@value": "...", "@language": "en"} wrapper.
    COALESCE(
        response_body->'title'->>'@value',
        response_body->>'title'
    )                                                     AS title,

    -- Classification kind: ICD-11 'classKind'; ICD-10 has no equivalent
    response_body->>'classKind'                           AS class_kind,

    -- ICD-11 browser URL for traceability
    response_body->>'browserUrl'                          AS browser_url,

    -- Definition text (ICD-11 only, also wrapped in @value object)
    COALESCE(
        response_body->'definition'->>'@value',
        response_body->>'definition'
    )                                                     AS definition,

    -- Parent/child hierarchy URIs (ICD-11) — stored as JSONB arrays
    response_body->'parent'                               AS parent_uris,
    response_body->'child'                                AS child_uris,

    -- Inclusion terms: ICD-11 uses 'inclusion', ICD-10 uses 'includes'
    COALESCE(
        response_body->'inclusion',
        response_body->'includes'
    )                                                     AS inclusion_terms,

    -- Exclusion terms: ICD-11 uses 'exclusion', ICD-10 uses 'excludes1'/'excludes2'
    COALESCE(
        response_body->'exclusion',
        response_body->'excludes1'
    )                                                     AS exclusion_terms,

    -- Additional ICD-10 exclusion array (ICD-10 only — ICD-11 uses single 'exclusion')
    response_body->'excludes2'                            AS exclusion_terms2,

    -- Coding hint: ICD-10 chapters/blocks sometimes carry mandatory coding instructions
    -- e.g. "Use additional code (U82-U84) to identify antimicrobial resistance"
    response_body->'codingHint'                           AS coding_hint,

    -- Raw source tracking (JSONB envelope columns)
    response_body                                         AS raw_json,
    id                                                    AS raw_source_id,
    'who_icd'::TEXT                                       AS source,
    request_timestamp::TIMESTAMPTZ                        AS request_timestamp,
    request_timestamp::TIMESTAMPTZ                        AS source_updated_at,
    FALSE                                                 AS processed_to_silver,
    NOW()                                                 AS created_at

FROM mol_raw.who_icd
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'code' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;

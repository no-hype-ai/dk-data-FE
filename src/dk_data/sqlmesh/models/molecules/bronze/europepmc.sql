-- SQLMesh Model: Bronze EuropePMC Publications
-- Extracts typed fields from mol_raw.europepmc_raw JSONB responses.
-- Feature: 019-cms-puf-platform-reconciliation (T022)
--
-- Grain: pmid
-- Source: mol_raw.europepmc_raw (populated by EuropePMCFetcher via run_ingestion)

MODEL (
    name mol_bronze.europepmc,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key pmid
    ),
    cron '@weekly',
    audits (
        not_null(columns := (pmid, title))
    ),
    grain pmid
);

SELECT
    gen_random_uuid()                                   AS id,

    -- Core identifiers
    (response_body->>'pmid')::TEXT                      AS pmid,
    response_body->>'doi'                               AS doi,
    response_body->>'pmcid'                             AS pmcid,

    -- Article metadata
    response_body->>'title'                             AS title,
    response_body->>'abstractText'                      AS abstract_text,
    response_body->>'authorString'                      AS author_string,

    -- Author list as JSONB array for downstream processing
    response_body->'authorList'->'author'               AS author_list,

    -- Journal information
    response_body->'journalInfo'->'journal'->>'title'   AS journal_title,
    response_body->'journalInfo'->'journal'->>'issn'    AS journal_issn,
    response_body->'journalInfo'->>'volume'             AS volume,
    response_body->'journalInfo'->>'issue'              AS issue,

    -- Publication dates
    (response_body->>'firstPublicationDate')::DATE      AS publication_date,
    (response_body->>'pubYear')::INTEGER                AS publication_year,

    -- Access and citation
    (response_body->>'isOpenAccess' = 'Y')::BOOLEAN     AS is_open_access,
    (response_body->>'citedByCount')::INTEGER           AS cited_by_count,

    -- Source tracking
    'europepmc'                                         AS source,
    request_timestamp                                   AS source_updated_at,
    FALSE                                               AS processed_to_silver,
    NOW()                                               AS created_at

FROM mol_raw.europepmc_raw
WHERE
    response_status = 200
    AND response_body->>'pmid' IS NOT NULL
    AND response_body->>'title' IS NOT NULL
    AND processed_to_bronze = FALSE;

-- SQLMesh Model: Bronze EuropePMC Publications
-- Transforms raw mol_raw.europepmc_raw JSONB response bodies to Bronze typed columns.
-- The raw table stores one row per API result object from the EuropePMC /search endpoint.
-- Field names match the EuropePMC REST API "core" result schema.
-- Part of: 011-datasource-integration

MODEL (
    name mol_bronze.europepmc,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key europepmc_pmid
    ),
    cron '@daily',
    audits (
        not_null(columns := (europepmc_pmid)),
        unique_values(columns := (europepmc_pmid))
    ),
    grain europepmc_pmid
);

SELECT
    gen_random_uuid()                                                             AS id,

    -- Primary identifiers
    -- EuropePMC 'id' field is their internal ID; pmid is the PubMed ID
    r.response_body->>'id'                                                        AS europepmc_id,
    r.response_body->>'pmid'                                                      AS europepmc_pmid,
    r.response_body->>'pmcid'                                                     AS pmcid,
    r.response_body->>'doi'                                                       AS doi,

    -- Content
    r.response_body->>'title'                                                     AS title,
    -- abstractText is the full abstract text in EuropePMC search results
    r.response_body->>'abstractText'                                              AS abstract,
    -- authorString is the flat author string; authorList.author is the structured list
    r.response_body->>'authorString'                                              AS author_string,
    r.response_body->'authorList'->'author'                                       AS author_list,

    -- Journal
    r.response_body->>'journalTitle'                                              AS journal_title,
    r.response_body->>'journalIssn'                                               AS journal_issn,

    -- Bibliographic details from journalInfo object
    -- EuropePMC API: journalInfo.volume, journalInfo.issue, pageInfo (e.g. "123-134")
    (r.response_body->'journalInfo'->>'volume')::TEXT                            AS volume,
    (r.response_body->'journalInfo'->>'issue')::TEXT                             AS issue,
    -- pageInfo format: "first-last" or just "first"
    CASE
        WHEN r.response_body->>'pageInfo' LIKE '%-%'
        THEN SPLIT_PART(r.response_body->>'pageInfo', '-', 1)
        ELSE r.response_body->>'pageInfo'
    END                                                                           AS first_page,
    CASE
        WHEN r.response_body->>'pageInfo' LIKE '%-%'
        THEN SPLIT_PART(r.response_body->>'pageInfo', '-', 2)
        ELSE NULL
    END                                                                           AS last_page,

    -- Dates
    -- firstPublicationDate: ISO date string "YYYY-MM-DD"
    (r.response_body->>'firstPublicationDate')::DATE                             AS publication_date,
    -- pubYear: 4-digit year string
    (r.response_body->>'pubYear')::INTEGER                                        AS publication_year,

    -- Metrics
    -- citedByCount: integer string in API response
    (r.response_body->>'citedByCount')::INTEGER                                   AS cited_by_count,

    -- Access flags
    -- isOpenAccess: "Y" or "N"
    (r.response_body->>'isOpenAccess') = 'Y'                                     AS is_open_access,
    -- inEPMC: "Y" or "N" — full text available in PMC
    (r.response_body->>'inEPMC') = 'Y'                                           AS in_epmc,

    -- Classification
    r.response_body->>'pubType'                                                   AS publication_type,
    -- source: 'MED' (PubMed/MEDLINE), 'PMC', 'PPR' (preprint), etc.
    r.response_body->>'source'                                                    AS epmc_source,

    -- MeSH headings — API path: meshHeadingList.meshHeading[].descriptorName
    (
        SELECT jsonb_agg(m->>'descriptorName')
        FROM jsonb_array_elements(
            COALESCE(r.response_body->'meshHeadingList'->'meshHeading', '[]'::JSONB)
        ) AS m
        WHERE m->>'descriptorName' IS NOT NULL
    )                                                                             AS mesh_terms,

    -- Keywords — API path: keywordList.keyword[] (array of strings)
    r.response_body->'keywordList'->'keyword'                                     AS keywords,

    -- Source tracking
    r.response_body                                                               AS raw_json,
    r.id::BIGINT                                                                  AS raw_source_id,
    'europepmc'                                                                   AS source,
    r._loaded_at                                                                  AS source_updated_at,
    FALSE                                                                         AS processed_to_silver,
    NOW()                                                                         AS created_at

FROM mol_raw.europepmc_raw r
WHERE
    r.response_status = 200
    AND r.processed_to_bronze = FALSE
    AND r.response_body->>'pmid' IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;

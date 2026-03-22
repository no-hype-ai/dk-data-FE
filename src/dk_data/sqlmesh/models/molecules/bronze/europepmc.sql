-- SQLMesh Model: Bronze Europe PMC
-- Transforms raw Europe PMC search responses to Bronze typed columns
-- Feature: europepmc-integration
--
-- EuropePMC search (resultType=core) returns:
--   { "resultList": { "result": [ { id, pmid, pmcid, doi, title, abstractText,
--     authorString, authorList, journalTitle, pubYear, firstPublicationDate,
--     isOpenAccess, inEPMC, hasPDF, citedByCount, meshHeadingList, keywordList,
--     pubTypeList, fullTextUrlList, language, source, ... } ] } }

MODEL (
    name mol_bronze.europepmc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    audits (
        not_null(columns := (europepmc_id))
    ),
    grain europepmc_id
);

SELECT
    gen_random_uuid() AS id,

    -- EuropePMC Identifiers
    r_item->>'id'    AS europepmc_id,   -- e.g. "PMC123456" or "12345678" (PMID)
    r_item->>'source' AS epmc_source,   -- MED (PubMed), PMC, PPR (preprint), etc.
    r_item->>'pmid'  AS pmid,
    r_item->>'pmcid' AS pmcid,
    r_item->>'doi'   AS doi,

    -- Title and Abstract (full text; no inverted index needed)
    r_item->>'title'        AS title,
    r_item->>'abstractText' AS abstract,

    -- Authors
    r_item->>'authorString' AS author_string,
    r_item->'authorList'->'author' AS authorships,

    -- Journal and Publication Info
    r_item->>'journalTitle'  AS journal_name,
    r_item->>'journalVolume' AS volume,
    r_item->>'issue'         AS issue,
    r_item->>'pageInfo'      AS page_info,
    r_item->>'pubYear'       AS pub_year_str,
    CASE WHEN r_item->>'pubYear' ~ '^\d{4}$'
         THEN (r_item->>'pubYear')::INTEGER ELSE NULL END AS publication_year,
    CASE WHEN r_item->>'firstPublicationDate' ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (r_item->>'firstPublicationDate')::DATE ELSE NULL END AS publication_date,

    -- Open Access and Full-Text
    (r_item->>'isOpenAccess' = 'Y') AS is_open_access,
    (r_item->>'inEPMC' = 'Y')       AS in_epmc_fulltext,
    (r_item->>'inPMC' = 'Y')        AS in_pmc,
    (r_item->>'hasPDF' = 'Y')       AS has_pdf,
    r_item->'fullTextUrlList'->'fullTextUrl' AS full_text_urls,

    -- Language and Type
    r_item->>'language'     AS language,
    r_item->'pubTypeList'->'pubType' AS pub_types,

    -- Classification
    r_item->'meshHeadingList'->'meshHeading' AS mesh_headings,
    r_item->'keywordList'->'keyword'         AS keywords,
    r_item->'chemicalList'->'chemical'       AS chemicals,

    -- Metrics
    (r_item->>'citedByCount')::INTEGER AS cited_by_count,
    (r_item->>'hasTextMinedTerms' = 'Y') AS has_text_mined_terms,

    -- Cross-links
    r_item->>'dateOfCreation'      AS date_of_creation,
    r_item->>'firstPublicationDate' AS first_publication_date,

    -- Affiliation
    r_item->>'affiliation' AS affiliation,

    -- Raw source tracking
    r_item AS raw_json,
    r.id AS raw_source_id,
    'europepmc' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.europepmc r,
     jsonb_array_elements(response_body->'resultList'->'result') AS r_item
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->'resultList'->'result' IS NOT NULL
    AND jsonb_array_length(response_body->'resultList'->'result') > 0
    AND r_item->>'id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;

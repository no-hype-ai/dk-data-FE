-- SQLMesh Model: Bronze SEC EDGAR Filings
-- Normalises raw SEC EDGAR MD&A extractions to typed Bronze columns.
-- Revenue extraction is intentionally absent — that is handled by xenon's LLM
-- (processFinancialFilingsWithLLM in assessment-orchestrator.service.ts).

MODEL (
    name mol_bronze.sec_edgar,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (cik)),
    ),
    grain filing_id
);

SELECT
    gen_random_uuid() AS id,

    -- Filing identifiers
    COALESCE(
        response_body->>'accession_number',
        (response_body->>'cik') || '_' || (response_body->>'filing_type') || '_' || (response_body->>'filing_date')
    ) AS filing_id,

    response_body->>'cik'              AS cik,
    response_body->>'company_name'     AS company_name,
    -- drug_name: the molecule that triggered this ingestion (used for entity linking in silver)
    response_body->>'drug_name'        AS drug_name,
    response_body->>'filing_type'      AS filing_type,
    CASE WHEN (response_body->>'filing_date') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN (response_body->>'filing_date')::DATE WHEN (response_body->>'filing_date') ~ '^[0-9]{4}$' THEN (MAKE_DATE((response_body->>'filing_date')::INT, 1, 1)) ELSE NULL END AS filing_date,
    response_body->>'accession_number' AS accession_number,

    -- Document URL — xenon fetches HTML from this to extract MD&A text
    response_body->>'document_url'     AS document_url,

    -- MD&A text — NULL when fetcher stores metadata-only; xenon LLM fetches from document_url instead
    response_body->>'mda_text'         AS mda_text,
    response_body->>'risk_factors_text' AS risk_factors_text,

    -- Raw source tracking
    response_body   AS raw_json,
    id              AS raw_source_id,
    'sec_edgar'     AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE           AS processed_to_silver,
    NOW()           AS created_at

FROM mol_raw.sec_edgar
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'cik' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;

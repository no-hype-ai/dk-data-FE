-- SQLMesh Model: Bronze SEC EDGAR Filings
-- Transforms raw SEC EDGAR API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.sec_edgar,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (cik)),
        unique_values(columns := (filing_id))
    ),
    grain filing_id
);

SELECT
    gen_random_uuid() AS id,

    -- Filing identifiers (keys match sec_edgar fetcher snake_case normalization)
    COALESCE(
        response_body->>'accession_number',
        response_body->>'cik' || '_' || response_body->>'filing_type' || '_' || response_body->>'filing_date'
    ) AS filing_id,
    response_body->>'cik' AS cik,
    response_body->>'company_name' AS company_name,
    response_body->>'filing_type' AS filing_type,
    response_body->>'filing_date' AS filing_date,

    -- Financial data (requires separate XBRL processing; will be NULL from the basic fetcher)
    (response_body->>'revenue')::NUMERIC AS revenue,
    (response_body->>'net_income')::NUMERIC AS net_income,
    (response_body->>'total_assets')::NUMERIC AS total_assets,

    -- MD&A and risk factors text for downstream indication revenue parsing
    response_body->>'mda_text' AS mda_excerpt,
    response_body->>'risk_factors_text' AS risk_factors_excerpt,
    response_body->>'product_name' AS product_name,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'sec_edgar' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.sec_edgar
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'cik' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;

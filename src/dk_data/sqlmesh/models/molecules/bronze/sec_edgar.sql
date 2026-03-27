-- SQLMesh Model: Bronze SEC EDGAR Filings
-- Transforms raw SEC EDGAR flat-column records to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration
--
-- Source table: mol_raw.sec_edgar (flat columns, not JSONB response_body)
-- Loaded by: src/dk_data/ingestion/sources/sec_edgar.py

MODEL (
    name mol_bronze.sec_edgar,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key filing_id
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

    -- Filing identifiers
    COALESCE(
        r.accession_number,
        r.cik || '_' || r.filing_type || '_' || r.filing_date::TEXT
    ) AS filing_id,
    r.cik::TEXT                      AS cik,
    r.company_name::TEXT             AS company_name,
    r.filing_type::TEXT              AS filing_type,
    r.filing_date::DATE              AS filing_date,
    r.document_url::TEXT             AS document_url,
    r.description::TEXT              AS description,

    -- Financial data from XBRL is not available in the basic fetcher;
    -- these will be populated by a future XBRL enrichment step.
    NULL::NUMERIC AS revenue,
    NULL::NUMERIC AS net_income,
    NULL::NUMERIC AS total_assets,

    -- Source tracking
    'sec_edgar'                      AS source,
    r._loaded_at                     AS source_updated_at,
    FALSE                            AS processed_to_silver,
    NOW()                            AS created_at

FROM mol_raw.sec_edgar r
WHERE
    r.cik IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;

-- SQLMesh Model: Silver Financial Data
-- Normalized SEC EDGAR financial filing data
-- Part of: 015-assessment-dashboard-integration
--
-- Source: bronze.sec_edgar
-- Revenue/net_income/total_assets are NULL until a future XBRL enrichment step
-- populates them from EDGAR XBRL submissions API.

MODEL (
    name silver.financial_data,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (cik, filing_type, filing_date)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (cik, filing_type, filing_date))
    ),
    grain (cik, filing_type, filing_date)
);

SELECT
    gen_random_uuid()               AS id,
    b.cik::TEXT                     AS cik,
    b.company_name::TEXT            AS company_name,
    b.filing_type::TEXT             AS filing_type,
    b.filing_date::DATE             AS filing_date,
    b.document_url::TEXT            AS document_url,
    b.revenue::NUMERIC              AS revenue,
    b.net_income::NUMERIC           AS net_income,
    b.total_assets::NUMERIC         AS total_assets,
    NULL::NUMERIC                   AS market_cap,
    NULL::NUMERIC                   AS drug_revenue_pct,
    b.source,
    b.source_updated_at,
    NOW()                           AS created_at,
    NOW()                           AS updated_at
FROM bronze.sec_edgar b
WHERE b.processed_to_silver = FALSE
  AND b.cik IS NOT NULL
  AND b.filing_type IS NOT NULL
  AND b.filing_date IS NOT NULL;

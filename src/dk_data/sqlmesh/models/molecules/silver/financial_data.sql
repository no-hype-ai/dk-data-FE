-- SQLMesh Model: Silver Financial Data
-- Normalized SEC EDGAR financial filing data
-- Part of: 015-assessment-dashboard-integration

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
    gen_random_uuid() AS id,
    cik,
    company_name,
    filing_type,
    filing_date,
    revenue,
    net_income,
    total_assets,
    NULL::NUMERIC AS market_cap,
    NULL::NUMERIC AS drug_revenue_pct,
    mda_excerpt,
    risk_factors_excerpt,
    product_name,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM bronze.sec_edgar
WHERE processed_to_silver = FALSE
  AND cik IS NOT NULL
  AND filing_type IS NOT NULL;

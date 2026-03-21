-- SQLMesh Model: Silver Financial Data
-- Normalized SEC EDGAR financial filing data
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_silver.financial_data,
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
    b.filing_id,
    b.cik,
    b.company_name,
    b.filing_type,
    b.filing_date,
    b.revenue,
    b.net_income,
    b.total_assets,
    NULL::NUMERIC AS market_cap,
    NULL::NUMERIC AS drug_revenue_pct,
    b.mda_excerpt,
    b.risk_factors_excerpt,
    b.product_name,
    b.id AS bronze_id,
    b.source,
    b.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM mol_bronze.sec_edgar b
WHERE b.processed_to_silver = FALSE
  AND b.cik IS NOT NULL
  AND b.filing_type IS NOT NULL;

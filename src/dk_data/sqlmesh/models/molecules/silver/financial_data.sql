-- SQLMesh Model: Silver Financial Data
-- Normalized SEC EDGAR financial filing data
-- Part of: 015-assessment-dashboard-integration
--
-- Source: mol_bronze.sec_edgar
-- Revenue/net_income/total_assets are NULL until a future XBRL enrichment step
-- populates them from EDGAR XBRL submissions API.

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

-- Deduplicate on the unique key before MERGE.
-- SEC EDGAR bronze may contain duplicate filings ingested across multiple runs
-- (same CIK + filing_type + filing_date from different API responses).
-- DISTINCT ON keeps the most recently source-updated occurrence.
WITH deduped AS (
    SELECT DISTINCT ON (cik, filing_type, filing_date)
        cik::TEXT               AS cik,
        company_name::TEXT      AS company_name,
        filing_type::TEXT       AS filing_type,
        filing_date::DATE       AS filing_date,
        filing_id::TEXT         AS filing_id,
        document_url::TEXT      AS document_url,
        description::TEXT       AS description,
        revenue::NUMERIC        AS revenue,
        net_income::NUMERIC     AS net_income,
        total_assets::NUMERIC   AS total_assets,
        source,
        source_updated_at
    FROM mol_bronze.sec_edgar
    WHERE processed_to_silver = FALSE
      AND cik IS NOT NULL
      AND filing_type IS NOT NULL
      AND filing_date IS NOT NULL
    ORDER BY cik, filing_type, filing_date, source_updated_at DESC NULLS LAST
)

SELECT
    gen_random_uuid()               AS id,
    cik,
    company_name,
    filing_type,
    filing_date,
    filing_id,
    document_url,
    description,
    revenue,
    net_income,
    total_assets,
    NULL::NUMERIC                   AS market_cap,
    NULL::NUMERIC                   AS drug_revenue_pct,
    source,
    source_updated_at,
    NOW()                           AS created_at,
    NOW()                           AS updated_at
FROM deduped;

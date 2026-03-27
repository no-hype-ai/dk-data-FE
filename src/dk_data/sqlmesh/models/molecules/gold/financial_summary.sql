-- SQLMesh Model: Gold Financial Summary
-- Cross-source financial data per molecule/company
-- Part of: 015-assessment-dashboard-integration
--
-- Source: mol_silver.financial_data, mol_silver.molecules
-- Joins company names from SEC filings to molecule canonical names.
-- Revenue/net_income/total_assets are NULL until XBRL enrichment completes.

MODEL (
    name mol_gold.financial_summary,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, cik)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (cik, company_name))
    ),
    grain (molecule_id, cik)
);

WITH latest_filings AS (
    SELECT
        cik,
        company_name,
        -- Most recent filing values
        MAX(filing_date) AS latest_filing_date,
        COUNT(*)         AS filing_count
    FROM mol_silver.financial_data
    GROUP BY cik, company_name
),

latest_financials AS (
    SELECT DISTINCT ON (fd.cik)
        fd.cik,
        fd.company_name,
        fd.revenue         AS latest_revenue,
        fd.net_income      AS latest_net_income,
        fd.total_assets,
        fd.drug_revenue_pct,
        lf.filing_count,
        lf.latest_filing_date
    FROM mol_silver.financial_data fd
    JOIN latest_filings lf ON fd.cik = lf.cik
    ORDER BY fd.cik, fd.filing_date DESC
),

-- Link companies to molecules via mol_silver.molecules canonical_name
molecule_linked AS (
    SELECT
        m.id                    AS molecule_id,
        f.company_name,
        f.cik,
        f.latest_revenue,
        f.latest_net_income,
        f.total_assets,
        f.drug_revenue_pct,
        f.filing_count,
        f.latest_filing_date
    FROM latest_financials f
    LEFT JOIN mol_silver.molecules m
        ON LOWER(f.company_name) = LOWER(m.canonical_name)
)

SELECT
    gen_random_uuid()           AS id,
    molecule_id,
    company_name,
    cik,
    latest_revenue::NUMERIC,
    latest_net_income::NUMERIC,
    total_assets::NUMERIC,
    drug_revenue_pct::NUMERIC,
    filing_count::INTEGER,
    latest_filing_date::DATE,
    NOW()                       AS created_at,
    NOW()                       AS updated_at
FROM molecule_linked;

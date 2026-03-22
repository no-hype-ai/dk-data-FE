-- SQLMesh Model: Gold Financial Summary
-- Cross-source financial data per molecule/company
-- Part of: 015-assessment-dashboard-integration

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

-- mol_silver.financial_data is populated by ip_silver pipeline (not yet run).
-- Return empty result set with correct schema until ip_silver runs.
SELECT
    gen_random_uuid() AS id,
    NULL::UUID AS molecule_id,
    NULL::TEXT AS company_name,
    NULL::TEXT AS cik,
    NULL::NUMERIC AS latest_revenue,
    NULL::NUMERIC AS latest_net_income,
    NULL::NUMERIC AS total_assets,
    NULL::NUMERIC AS drug_revenue_pct,
    0 AS filing_count,
    NULL::DATE AS latest_filing_date,
    NOW() AS created_at,
    NOW() AS updated_at
WHERE FALSE;

-- SQLMesh Model: Gold Financial Summary
-- INTENTIONALLY EMPTY — revenue aggregation is handled by xenon's LLM pipeline.
-- xenon reads mol_silver.financial_filings (mda_excerpt), runs
-- processFinancialFilingsWithLLM, and stores structured results in
-- xenon.molecule_financial_summaries (a xenon-schema table).
--
-- This model is retained as a stub so SQLMesh does not error on a missing
-- dependency reference. It produces no rows.

MODEL (
    name mol_gold.financial_summary,
    kind FULL,
    cron '@weekly'
);

SELECT
    gen_random_uuid()   AS id,
    NULL::UUID          AS molecule_id,
    NULL::TEXT          AS company_name,
    NULL::TEXT          AS cik,
    NULL::NUMERIC       AS latest_revenue,
    NULL::NUMERIC       AS latest_net_income,
    NULL::NUMERIC       AS total_assets,
    NULL::NUMERIC       AS drug_revenue_pct,
    0                   AS filing_count,
    NULL::DATE          AS latest_filing_date,
    NOW()               AS created_at,
    NOW()               AS updated_at
WHERE FALSE;

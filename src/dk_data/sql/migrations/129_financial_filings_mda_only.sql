-- Migration 129: Simplify mol_silver.financial_filings to MDA-text-only schema
-- Date: 2026-03-22
--
-- The old schema carried revenue/net_income/product_name columns populated by
-- dk-data-FE's table-parsing heuristics. These columns are wrong-layer — revenue
-- extraction is handled by xenon's LLM (processFinancialFilingsWithLLM).
--
-- Changes:
--   DROP: revenue, net_income, period, product_name
--   ADD:  drug_name (the molecule that triggered ingestion, used for entity linking)
--         cik       (company SEC CIK, for traceability)

-- 1. Add new columns (idempotent)
ALTER TABLE mol_silver.financial_filings
    ADD COLUMN IF NOT EXISTS drug_name VARCHAR(500),
    ADD COLUMN IF NOT EXISTS cik       VARCHAR(50);

-- 2. Drop old revenue/product columns — these should be empty after this migration
ALTER TABLE mol_silver.financial_filings
    DROP COLUMN IF EXISTS revenue,
    DROP COLUMN IF EXISTS net_income,
    DROP COLUMN IF EXISTS period,
    DROP COLUMN IF EXISTS product_name;

-- 3. Drop the old dedup index (it referenced product_name which no longer exists)
DROP INDEX IF EXISTS idx_fin_filings_dedup;

-- 4. New dedup index on (cik, filing_type, filing_date) — matches SQLMesh grain
CREATE UNIQUE INDEX IF NOT EXISTS idx_fin_filings_cik_type_date
    ON mol_silver.financial_filings(cik, filing_type, filing_date)
    WHERE cik IS NOT NULL;

-- 5. Drop mol_silver.financial_data (old SQLMesh table name — replaced by financial_filings)
DROP TABLE IF EXISTS mol_silver.financial_data;

-- 6. Ensure PostgREST grant
GRANT SELECT ON mol_silver.financial_filings TO analyst;

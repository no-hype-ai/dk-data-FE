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

-- 1-4. ALTER TABLE / index operations only apply if financial_filings is a plain table.
-- SQLMesh INCREMENTAL_BY_UNIQUE_KEY creates a view named financial_filings pointing to
-- an internal snapshot table — the schema is defined in the SQLMesh model, not here.
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_silver' AND c.relname='financial_filings') = 'r' THEN
        ALTER TABLE mol_silver.financial_filings
            ADD COLUMN IF NOT EXISTS drug_name VARCHAR(500),
            ADD COLUMN IF NOT EXISTS cik       VARCHAR(50);
        ALTER TABLE mol_silver.financial_filings
            DROP COLUMN IF EXISTS revenue,
            DROP COLUMN IF EXISTS net_income,
            DROP COLUMN IF EXISTS period,
            DROP COLUMN IF EXISTS product_name;
        DROP INDEX IF EXISTS idx_fin_filings_dedup;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fin_filings_cik_type_date
            ON mol_silver.financial_filings(cik, filing_type, filing_date)
            WHERE cik IS NOT NULL;
    END IF;
END $$;

-- 5. Drop mol_silver.financial_data (old SQLMesh table name — replaced by financial_filings)
DROP TABLE IF EXISTS mol_silver.financial_data;

-- 6. Ensure PostgREST grant
GRANT SELECT ON mol_silver.financial_filings TO analyst;

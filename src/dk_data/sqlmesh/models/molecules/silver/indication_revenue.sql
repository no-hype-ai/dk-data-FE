-- SQLMesh Model: Silver Indication Revenue
-- Per-indication revenue extracted from SEC MD&A filings by xenon's LLM pipeline.
-- Xenon writes rows here after extracting revenue figures from mol_silver.financial_filings.
-- This model defines the schema; xenon (via Prisma/raw SQL) inserts the actual data.
-- Referenced by data-registry: path /indication_revenue, schema mol_silver.
--
-- Data flow: SEC 10-K MD&A text → xenon LLM extraction → mol_silver.indication_revenue
--            → xenon assessment pipeline → mol_gold.indication_revenue_summary

MODEL (
    name mol_silver.indication_revenue,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (cik, filing_date, indication_name)
    ),
    cron '@daily',
    audits (
        not_null(columns := (cik, indication_name))
    ),
    grain (cik, filing_date, indication_name)
);

-- Source: financial_filings joined to itself where xenon has written revenue rows.
-- Xenon writes directly to this table; the SQLMesh model keeps schema in sync.
-- Select from financial_filings to carry metadata; revenue values are xenon-populated.
SELECT
    gen_random_uuid()                   AS id,
    f.molecule_id,
    f.cik,
    f.company_name,
    f.filing_date,
    f.filing_type,
    -- indication_name populated by xenon LLM extraction (NULL in base pipeline)
    NULL::TEXT                          AS indication_name,
    -- revenue_usd_millions populated by xenon LLM extraction
    NULL::NUMERIC                       AS revenue_usd_millions,
    NULL::INTEGER                       AS revenue_year,
    NULL::TEXT                          AS revenue_segment,
    NULL::TEXT                          AS extraction_confidence,
    f.accession_number,
    'sec_edgar'                         AS source,
    f.source_updated_at,
    NOW()                               AS created_at

-- financial_filings is managed by the xenon service; stub returns 0 rows until xenon writes.
FROM (
    SELECT
        NULL::UUID      AS molecule_id,
        NULL::TEXT      AS cik,
        NULL::TEXT      AS company_name,
        NULL::DATE      AS filing_date,
        NULL::TEXT      AS filing_type,
        NULL::TEXT      AS accession_number,
        NULL::TEXT      AS mda_excerpt,
        NOW()           AS source_updated_at
    WHERE FALSE
) f
LIMIT 0;
-- LIMIT 0: schema-only stub — xenon writes real rows via direct INSERT.
-- SQLMesh manages the table DDL; xenon owns the data.

-- SQLMesh Model: Silver Company Financials
-- SEC EDGAR filing data linked to mol_silver.molecules via company name
-- Feature: 019-cms-puf-platform-reconciliation — zero column loss audit
--
-- Purpose: SEC EDGAR bronze was entirely unconsumed by silver. All bronze columns
--   are promoted here so pharma company filing data is directly queryable.
--   molecule_id linkage is intentionally omitted — filings are company-level,
--   not drug-level; company → molecule relationships should be resolved in gold.
--
-- Column names match mol_bronze.sec_edgar exactly.

MODEL (
    name mol_silver.company_financials,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key filing_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (filing_id, cik)),
        unique_values(columns := (filing_id))
    ),
    grain filing_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (e.filing_id)
    gen_random_uuid()           AS id,

    -- Filing identifiers (exact bronze column names from mol_bronze.sec_edgar)
    e.filing_id,
    e.accession_number,
    e.cik,
    e.company_name,
    e.filing_type,
    e.filing_date,
    e.document_url,
    e.description,

    -- Financial data (NULL in current fetcher — populated by future XBRL enrichment)
    e.revenue,
    e.net_income,
    e.total_assets,

    -- Source tracking
    e.source,
    e.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.sec_edgar e
WHERE
    e.processed_to_silver = FALSE
    AND e.cik IS NOT NULL
ORDER BY e.filing_id, e.source_updated_at DESC NULLS LAST;

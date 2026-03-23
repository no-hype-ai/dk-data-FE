-- SQLMesh Model: Silver SEC EDGAR Financial Filings
-- Normalised MD&A filing data with molecule entity link.
-- Revenue extraction from mda_excerpt is handled by xenon's LLM pipeline —
-- this model intentionally carries NO revenue or product_name columns.
--
-- Entity linking: joins drug_name → mol_silver.molecules.canonical_name to
-- produce a stable molecule_id for PostgREST filtering by xenon.

MODEL (
    name mol_silver.financial_filings,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (cik, filing_type, filing_date)
    ),
    cron '@daily',
    audits (
        not_null(columns := (cik, filing_type))
    ),
    grain (cik, filing_type, filing_date)
);

SELECT
    gen_random_uuid()                       AS id,
    b.filing_id,
    b.cik,
    b.company_name,
    b.drug_name,
    b.filing_type,
    b.filing_date,
    b.accession_number,
    b.document_url,
    b.mda_text                              AS mda_excerpt,
    b.risk_factors_text                     AS risk_factors_excerpt,
    -- Entity link: resolve molecule_id from drug_name (canonical or pref name).
    -- NULL when the drug name is not yet in mol_silver.molecules.
    m.molecule_id                           AS molecule_id,
    b.source,
    b.source_updated_at,
    NOW()                                   AS created_at,
    NOW()                                   AS updated_at
FROM mol_bronze.sec_edgar b
LEFT JOIN mol_silver.molecules m
       ON LOWER(m.canonical_name) = LOWER(b.drug_name)
WHERE b.processed_to_silver = FALSE
  AND b.cik IS NOT NULL
  AND b.filing_type IS NOT NULL;

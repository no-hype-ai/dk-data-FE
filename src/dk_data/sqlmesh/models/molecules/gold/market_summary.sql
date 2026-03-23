-- SQLMesh Model: Gold Market Summary
-- Per-molecule market and financial context aggregated from silver sources.
-- Combines SEC filing revenue data with CMS drug spending for a unified
-- financial picture. Used by: market_opportunity, financial_analysis,
-- competitive_positioning, key_metrics, investment_thesis.

MODEL (
    name mol_gold.market_summary,
    kind FULL,
    cron '@weekly',
    grain (molecule_id)
);

WITH sec_revenue AS (
    -- Latest annual revenue from SEC filings per molecule
    -- Column names match mol_silver.financial_filings DDL (migration 114):
    --   revenue (not revenue_usd), filing_date (not fiscal_year)
    SELECT
        ff.molecule_id,
        MAX(ff.revenue)                                          AS latest_revenue_usd,
        MAX(EXTRACT(YEAR FROM ff.filing_date)::INT)              AS latest_revenue_year,
        COUNT(DISTINCT EXTRACT(YEAR FROM ff.filing_date)::INT)   AS filing_years,
        MAX(ff.company_name)                                     AS company_name,
        jsonb_agg(
            jsonb_build_object(
                'year',    EXTRACT(YEAR FROM ff.filing_date)::INT,
                'revenue', ff.revenue,
                'company', ff.company_name
            )
            ORDER BY ff.filing_date DESC
        ) FILTER (WHERE ff.revenue IS NOT NULL)                  AS revenue_history
    FROM mol_silver.financial_filings ff
    WHERE ff.molecule_id IS NOT NULL
    GROUP BY ff.molecule_id
),

cms_spending AS (
    -- CMS Medicare Part B/D total spend per molecule (most recent year)
    SELECT
        ds.molecule_id,
        SUM(ds.total_spending)                      AS cms_total_spending,
        MAX(ds.year)                                AS cms_latest_year,
        SUM(ds.total_claims)                        AS cms_total_claims,
        SUM(ds.total_beneficiaries)                 AS cms_total_beneficiaries,
        COUNT(DISTINCT ds.program)                  AS cms_program_count
    FROM mol_silver.drug_spending ds
    WHERE ds.molecule_id IS NOT NULL
      AND ds.year = (
          SELECT MAX(year) FROM mol_silver.drug_spending ds2
          WHERE ds2.molecule_id = ds.molecule_id
      )
    GROUP BY ds.molecule_id
)

SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    NULL::TEXT[] AS therapeutic_areas,
    m.max_phase,

    -- SEC revenue data
    r.company_name,
    r.latest_revenue_usd,
    r.latest_revenue_year,
    r.filing_years,
    r.revenue_history,

    -- CMS Medicare spending
    c.cms_total_spending,
    c.cms_latest_year,
    c.cms_total_claims,
    c.cms_total_beneficiaries,
    c.cms_program_count,

    -- Data coverage flags (help LLM know what's available)
    (r.latest_revenue_usd IS NOT NULL)              AS has_sec_revenue,
    (c.cms_total_spending IS NOT NULL)              AS has_cms_spending,

    NOW() AS computed_at

FROM mol_silver.molecules m
LEFT JOIN sec_revenue r ON m.molecule_id = r.molecule_id
LEFT JOIN cms_spending c ON m.molecule_id = c.molecule_id
WHERE m.needs_review = FALSE
  AND (r.latest_revenue_usd IS NOT NULL OR c.cms_total_spending IS NOT NULL);

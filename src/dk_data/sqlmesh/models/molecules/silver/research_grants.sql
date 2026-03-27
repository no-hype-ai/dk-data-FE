-- SQLMesh Model: Silver Research Grants
-- Promotes mol_bronze.nih_reporter into mol_silver.research_grants
-- Entity linking: LEFT JOIN mol_silver.molecules by canonical_name match in project title.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Part of: Tier 4 gap fix — nih_reporter had no bronze→silver transform

MODEL (
    name mol_silver.research_grants,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (project_num, funding_agency))
    )
);

SELECT
    gen_random_uuid()       AS grant_id,
    m.molecule_id,
    b.project_num,
    b.project_title,
    b.pi_name,
    b.pi_institution,
    b.funding_agency,
    b.award_amount,
    b.fiscal_year,
    b.project_start,
    b.project_end,
    b.abstract_text         AS abstract,
    'nih_reporter'          AS source,
    b.ingested_at           AS created_at

FROM mol_bronze.nih_reporter b
LEFT JOIN mol_silver.molecules m
       ON LOWER(b.project_title) LIKE '%' || LOWER(m.canonical_name) || '%'
      AND LENGTH(m.canonical_name) > 4
WHERE b.project_num IS NOT NULL
  AND b.funding_agency IS NOT NULL;

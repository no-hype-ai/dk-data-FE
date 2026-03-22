-- SQLMesh Model: Silver Research Grants
-- Promotes mol_bronze.nih_reporter into mol_silver.research_grants
-- with molecule-level linkage. molecule_id is NULL — entity linking fills it
-- by matching grant terms/title against mol_silver.molecules drug names.
-- Part of: Tier 4 gap fix — nih_reporter had no bronze→silver transform

MODEL (
    name mol_silver.research_grants,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (project_number)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (project_number, funding_agency))
    ),
    grain (project_number)
);

SELECT
    gen_random_uuid()       AS grant_id,
    NULL::UUID              AS molecule_id,     -- entity linking fills this via terms/title matching
    b.project_number,
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
WHERE b.processed_to_silver = FALSE
  AND b.project_number IS NOT NULL
  AND b.funding_agency IS NOT NULL;

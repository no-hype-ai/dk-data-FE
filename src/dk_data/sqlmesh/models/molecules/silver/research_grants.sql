-- SQLMesh Model: Silver Research Grants
-- NIH Reporter grant data linked to mol_silver.molecules
-- Feature: 019-cms-puf-platform-reconciliation — zero column loss audit
--
-- Purpose: NIH Reporter bronze was entirely unconsumed by mol_silver. All bronze
--   columns are promoted here. molecule_id is NULL when no match is found.
--
-- Column names match mol_bronze.nih_reporter exactly.

MODEL (
    name mol_silver.research_grants,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key project_num
    ),
    cron '@weekly',
    audits (
        not_null(columns := (project_num, project_title)),
        unique_values(columns := (project_num))
    ),
    grain project_num
);

SELECT DISTINCT ON (n.project_num)
    gen_random_uuid()       AS id,

    -- NIH identifiers (exact bronze column names from mol_bronze.nih_reporter)
    n.appl_id,
    n.project_num,
    n.study_section,

    -- Project metadata
    n.project_title,
    n.fiscal_year,
    n.activity_code,
    n.mechanism_code,
    n.funding_mechanism,

    -- Investigators and organization
    n.pi_names,
    n.program_officials,
    n.organization_name,
    n.organization_city,
    n.organization_state,
    n.organization_country,

    -- Funding
    n.award_amount,
    n.total_cost,

    -- Content
    n.abstract_text,
    n.terms,

    -- Dates
    n.project_start_date,
    n.project_end_date,

    -- Molecule linkage (NULL when no match found — data always retained)
    -- Title-based match: canonical_name must be >4 chars to avoid false positives
    (
        SELECT m.molecule_id
        FROM mol_silver.molecules m
        WHERE
            LOWER(n.project_title) LIKE '%' || LOWER(m.canonical_name) || '%'
            AND LENGTH(m.canonical_name) > 4
        LIMIT 1
    ) AS molecule_id,

    -- Source tracking
    n.source,
    n.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.nih_reporter n
WHERE
    n.processed_to_silver = FALSE
    AND n.project_num IS NOT NULL
ORDER BY n.project_num, n.source_updated_at DESC NULLS LAST;

-- SQLMesh Model: Gold Company Pipeline
-- Pre-aggregated company pipeline view for competitive intelligence
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_gold.company_pipeline,
    kind FULL,
    cron '@daily',
    grain (company, molecule_id)
);

SELECT
    ct.sponsor AS company,
    m.id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    m.development_status,

    -- Highest phase from trials
    MAX(
        CASE
            WHEN ct.phase LIKE '%Phase 4%' THEN 'Phase 4'
            WHEN ct.phase LIKE '%Phase 3%' THEN 'Phase 3'
            WHEN ct.phase LIKE '%Phase 2%' THEN 'Phase 2'
            WHEN ct.phase LIKE '%Phase 1%' THEN 'Phase 1'
            ELSE ct.phase
        END
    ) AS phase,

    -- Trial status (most advanced)
    MAX(
        CASE ct.status
            WHEN 'Completed' THEN 5
            WHEN 'Active, not recruiting' THEN 4
            WHEN 'Recruiting' THEN 3
            WHEN 'Enrolling by invitation' THEN 2
            WHEN 'Not yet recruiting' THEN 1
            ELSE 0
        END
    ) AS status_rank,
    (
        ARRAY_AGG(ct.status ORDER BY
            CASE ct.status
                WHEN 'Completed' THEN 5
                WHEN 'Active, not recruiting' THEN 4
                WHEN 'Recruiting' THEN 3
                WHEN 'Enrolling by invitation' THEN 2
                WHEN 'Not yet recruiting' THEN 1
                ELSE 0
            END DESC
        )
    )[1] AS trial_status,

    -- Indications for this company-molecule pair
    (
        SELECT jsonb_agg(DISTINCT indication)
        FROM (
            SELECT jsonb_array_elements_text(COALESCE(ct2.conditions, '[]'::jsonb)) AS indication
            FROM mol_silver.clinical_trials ct2
            WHERE ct2.molecule_id = m.id
              AND ct2.sponsor = ct.sponsor
        ) i
        WHERE indication IS NOT NULL
    ) AS indications,

    -- Trial metrics
    COUNT(DISTINCT ct.nct_id) AS trial_count,
    MAX(ct.start_date) AS latest_trial_start,
    MIN(ct.start_date) AS earliest_trial_start,

    -- Enrollment totals
    SUM(ct.enrollment) AS total_enrollment,

    -- Mechanism of action (from interventions data)
    (
        SELECT string_agg(DISTINCT intervention->>'interventionType', ', ')
        FROM mol_silver.clinical_trials ct2,
             jsonb_array_elements(ct2.interventions) AS intervention
        WHERE ct2.molecule_id = m.id
          AND ct2.sponsor = ct.sponsor
          AND intervention->>'interventionType' IS NOT NULL
    ) AS mechanism_of_action,

    -- Expected completion (max completion date for company-molecule)
    MAX(ct.completion_date) AS expected_completion,

    NOW() AS computed_at

FROM mol_silver.clinical_trials ct
JOIN mol_silver.molecules m ON ct.molecule_id = m.id
WHERE m.needs_review = FALSE
  AND ct.sponsor IS NOT NULL
  AND ct.sponsor != ''
GROUP BY ct.sponsor, m.id, m.inchi_key, m.canonical_name, m.development_status
ORDER BY ct.sponsor, trial_count DESC

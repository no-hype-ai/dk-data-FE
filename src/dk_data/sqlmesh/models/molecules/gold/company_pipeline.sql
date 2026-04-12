-- SQLMesh Model: Gold Company Pipeline
-- Pre-aggregated company pipeline view for competitive intelligence
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_gold.company_pipeline,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (company, molecule_id)
    ),
    cron '@weekly',
    grain (company, molecule_id)
);

SELECT
    ct.lead_sponsor_name AS company,
    m.molecule_id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    CASE
        WHEN m.max_phase >= 4 THEN 'approved'
        WHEN m.max_phase = 3  THEN 'phase_3'
        WHEN m.max_phase = 2  THEN 'phase_2'
        WHEN m.max_phase = 1  THEN 'phase_1'
        WHEN m.max_phase = 0  THEN 'preclinical'
        ELSE 'unknown'
    END                                     AS development_status,

    -- Highest phase from trials
    MAX(
        CASE
            WHEN ct.phase_derived LIKE '%Phase 4%' THEN 'Phase 4'
            WHEN ct.phase_derived LIKE '%Phase 3%' THEN 'Phase 3'
            WHEN ct.phase_derived LIKE '%Phase 2%' THEN 'Phase 2'
            WHEN ct.phase_derived LIKE '%Phase 1%' THEN 'Phase 1'
            ELSE ct.phase_derived
        END
    ) AS phase,

    -- Trial status (most advanced)
    MAX(
        CASE ct.overall_status
            WHEN 'Completed' THEN 5
            WHEN 'Active, not recruiting' THEN 4
            WHEN 'Recruiting' THEN 3
            WHEN 'Enrolling by invitation' THEN 2
            WHEN 'Not yet recruiting' THEN 1
            ELSE 0
        END
    ) AS status_rank,
    (
        ARRAY_AGG(ct.overall_status ORDER BY
            CASE ct.overall_status
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
            WHERE ct2.molecule_id = m.molecule_id
              AND ct2.lead_sponsor_name = ct.lead_sponsor_name
        ) i
        WHERE indication IS NOT NULL
    ) AS indications,

    -- Trial metrics
    COUNT(DISTINCT ct.nct_id) AS trial_count,
    MAX(ct.start_date) AS latest_trial_start,
    MIN(ct.start_date) AS earliest_trial_start,

    -- Enrollment totals
    SUM(ct.enrollment_count) AS total_enrollment,

    -- Intervention types from ClinicalTrials.gov (e.g. "DRUG", "BIOLOGICAL", "DEVICE").
    -- Not mechanism of action — CT.gov does not expose MoA; renamed to avoid confusion.
    (
        SELECT string_agg(DISTINCT intervention->>'type', ', ')
        FROM mol_silver.clinical_trials ct2,
             jsonb_array_elements(ct2.interventions) AS intervention
        WHERE ct2.molecule_id = m.molecule_id
          AND ct2.lead_sponsor_name = ct.lead_sponsor_name
          AND intervention->>'type' IS NOT NULL
    ) AS intervention_types,

    -- Expected completion (max completion date for company-molecule)
    MAX(ct.completion_date) AS expected_completion,

    NOW() AS computed_at

FROM mol_silver.clinical_trials ct
JOIN mol_silver.molecules m ON ct.molecule_id = m.molecule_id
WHERE TRUE
  AND ct.lead_sponsor_name IS NOT NULL
  AND ct.lead_sponsor_name != ''
GROUP BY ct.lead_sponsor_name, m.molecule_id, m.inchi_key, m.canonical_name, CASE
        WHEN m.max_phase >= 4 THEN 'approved'
        WHEN m.max_phase = 3  THEN 'phase_3'
        WHEN m.max_phase = 2  THEN 'phase_2'
        WHEN m.max_phase = 1  THEN 'phase_1'
        WHEN m.max_phase = 0  THEN 'preclinical'
        ELSE 'unknown'
    END
ORDER BY ct.lead_sponsor_name, trial_count DESC

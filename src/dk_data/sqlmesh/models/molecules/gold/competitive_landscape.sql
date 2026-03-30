-- SQLMesh Model: Gold Competitive Landscape
-- Pre-aggregated competitive analysis view for decision support
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_gold.competitive_landscape,
    kind FULL,
    cron '@daily',
    grain (molecule_id)
);

SELECT
    m.molecule_id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    m.therapeutic_areas,
    m.mechanism_of_action,
    m.development_status,
    m.max_phase,

    -- Active trial count
    COUNT(DISTINCT ct.nct_id) FILTER (
        WHERE ct.overall_status IN ('Recruiting', 'Active, not recruiting', 'Enrolling by invitation')
    ) AS active_trials,

    -- Phase distribution as JSONB
    jsonb_build_object(
        'phase_1', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase LIKE '%Phase 1%'),
        'phase_2', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase LIKE '%Phase 2%'),
        'phase_3', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase LIKE '%Phase 3%'),
        'phase_4', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase LIKE '%Phase 4%')
    ) AS phase_distribution,

    -- Unique indications (correlated subquery — avoids ungrouped column error)
    (
        SELECT jsonb_agg(DISTINCT indication)
        FROM (
            SELECT jsonb_array_elements_text(COALESCE(cond.conditions, '[]'::jsonb)) AS indication
            FROM mol_silver.clinical_trials cond
            WHERE cond.molecule_id = m.molecule_id
              AND cond.conditions IS NOT NULL
        ) i
        WHERE indication IS NOT NULL
    ) AS indications,

    -- Unique sponsors
    (
        SELECT jsonb_agg(DISTINCT lead_sponsor)
        FROM (
            SELECT ct2.lead_sponsor
            FROM mol_silver.clinical_trials ct2
            WHERE ct2.molecule_id = m.molecule_id
              AND ct2.lead_sponsor IS NOT NULL
        ) s
    ) AS sponsors,

    -- Latest trial activity
    MAX(ct.start_date) AS latest_trial_start,

    -- Competitive metrics
    COUNT(DISTINCT ct.nct_id) AS total_trials,
    COUNT(DISTINCT ct.lead_sponsor) AS sponsor_count,

    -- Safety signal summary
    (
        SELECT jsonb_build_object(
            'total_reports', COALESCE(SUM(ae.report_count), 0),
            'serious_reports', COALESCE(SUM(ae.serious_count), 0),
            'death_reports', COALESCE(SUM(ae.death_count), 0)
        )
        FROM mol_silver.adverse_events ae
        WHERE ae.molecule_id = m.molecule_id
    ) AS safety_summary,

    NOW() AS computed_at

FROM mol_silver.molecules m
LEFT JOIN mol_silver.clinical_trials ct ON m.molecule_id = ct.molecule_id
WHERE m.needs_review = FALSE
  AND m.development_status IN ('phase_1', 'phase_2', 'phase_3', 'approved')
GROUP BY m.molecule_id, m.inchi_key, m.canonical_name, m.therapeutic_areas,
         m.mechanism_of_action, m.development_status, m.max_phase
HAVING COUNT(DISTINCT ct.nct_id) > 0
   OR m.development_status = 'approved'
ORDER BY active_trials DESC NULLS LAST, m.max_phase DESC NULLS LAST

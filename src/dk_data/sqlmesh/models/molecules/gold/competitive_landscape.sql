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
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    NULL::TEXT[] AS therapeutic_areas,
    m.mechanism_of_action,
    m.max_phase,

    -- Active trial count
    COUNT(DISTINCT ct.nct_id) FILTER (
        WHERE ct.overall_status IN ('Recruiting', 'Active, not recruiting', 'Enrolling by invitation')
    ) AS active_trials,

    -- Phase distribution as JSONB
    -- phases is JSONB in silver — cast to TEXT for LIKE matching
    jsonb_build_object(
        'phase_1', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phases::TEXT LIKE '%Phase 1%'),
        'phase_2', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phases::TEXT LIKE '%Phase 2%'),
        'phase_3', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phases::TEXT LIKE '%Phase 3%'),
        'phase_4', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phases::TEXT LIKE '%Phase 4%')
    ) AS phase_distribution,

    -- Unique indications (self-join on molecule_id to avoid ungrouped ct reference)
    (
        SELECT jsonb_agg(DISTINCT elem)
        FROM mol_silver.clinical_trials ct3
        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(ct3.conditions, '[]'::jsonb)) AS elem
        WHERE ct3.molecule_id = m.molecule_id
          AND elem IS NOT NULL
    ) AS indications,

    -- Unique sponsors (using lead_sponsor_name — silver has no generic 'sponsor' column)
    (
        SELECT jsonb_agg(DISTINCT lead_sponsor_name)
        FROM mol_silver.clinical_trials ct2
        WHERE ct2.molecule_id = m.molecule_id
          AND ct2.lead_sponsor_name IS NOT NULL
    ) AS sponsors,

    -- Latest trial activity
    MAX(ct.start_date) AS latest_trial_start,

    -- Competitive metrics
    COUNT(DISTINCT ct.nct_id) AS total_trials,
    COUNT(DISTINCT ct.lead_sponsor_name) AS sponsor_count,

    -- Safety signal summary (count individual report rows)
    (
        SELECT jsonb_build_object(
            'total_reports', COUNT(*),
            'serious_reports', COUNT(*) FILTER (WHERE ae.serious = TRUE),
            'death_reports', COUNT(*) FILTER (WHERE ae.serious_death = TRUE)
        )
        FROM mol_silver.adverse_events ae
        WHERE ae.molecule_id = m.molecule_id
    ) AS safety_summary,

    NOW() AS computed_at

FROM mol_silver.molecules m
LEFT JOIN mol_silver.clinical_trials ct ON m.molecule_id = ct.molecule_id
WHERE m.needs_review = FALSE
GROUP BY m.molecule_id, m.inchi_key, m.canonical_name,
         m.mechanism_of_action, m.max_phase
HAVING COUNT(DISTINCT ct.nct_id) > 0
    OR m.max_phase >= 4
ORDER BY active_trials DESC NULLS LAST, m.max_phase DESC NULLS LAST

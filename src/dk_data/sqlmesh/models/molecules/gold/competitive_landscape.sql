-- SQLMesh Model: Gold Competitive Landscape
-- Pre-aggregated competitive analysis view for decision support
-- Part of DK Molecule Data Platform (012-dk-data-platform)
--
-- Refactored 2026-04-12 (S3 antipattern fix): the previous version had three
-- correlated scalar subqueries in the SELECT list (indications, sponsors,
-- safety_summary) that ran once per outer molecule. With ~500K molecules ×
-- 3 subqueries that's 1.5M inner scans. They are now hoisted into CTEs joined
-- once. The development_status CASE is also hoisted into the base CTE so it
-- isn't re-derived in WHERE/GROUP BY/HAVING.
MODEL (
    name mol_gold.competitive_landscape,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key molecule_id
    ),
    cron '@weekly',
    audits (not_null(columns := (molecule_id))),
    grain (molecule_id)
);

WITH molecules_classified AS (
    SELECT
        m.molecule_id,
        m.inchi_key,
        m.canonical_name,
        m.therapeutic_areas,
        m.mechanism_of_action,
        m.max_phase,
        CASE
            WHEN m.max_phase >= 4 THEN 'approved'
            WHEN m.max_phase = 3  THEN 'phase_3'
            WHEN m.max_phase = 2  THEN 'phase_2'
            WHEN m.max_phase = 1  THEN 'phase_1'
            WHEN m.max_phase = 0  THEN 'preclinical'
            ELSE 'unknown'
        END AS development_status
    FROM mol_silver.molecules m
),

-- Per-molecule trial aggregates (single GROUP BY pass over clinical_trials)
trial_agg AS (
    SELECT
        ct.molecule_id,
        COUNT(DISTINCT ct.nct_id) AS total_trials,
        COUNT(DISTINCT ct.nct_id) FILTER (
            WHERE ct.overall_status IN ('Recruiting', 'Active, not recruiting', 'Enrolling by invitation')
        ) AS active_trials,
        jsonb_build_object(
            'phase_1', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase_derived LIKE '%Phase 1%'),
            'phase_2', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase_derived LIKE '%Phase 2%'),
            'phase_3', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase_derived LIKE '%Phase 3%'),
            'phase_4', COUNT(DISTINCT ct.nct_id) FILTER (WHERE ct.phase_derived LIKE '%Phase 4%')
        ) AS phase_distribution,
        MAX(ct.start_date) AS latest_trial_start,
        COUNT(DISTINCT ct.lead_sponsor_name) AS sponsor_count
    FROM mol_silver.clinical_trials ct
    WHERE ct.molecule_id IS NOT NULL
    GROUP BY ct.molecule_id
),

-- Per-molecule indications: unnest conditions array, aggregate to JSONB array
indications_agg AS (
    SELECT
        ct.molecule_id,
        jsonb_agg(DISTINCT cond.indication) FILTER (WHERE cond.indication IS NOT NULL) AS indications
    FROM mol_silver.clinical_trials ct,
         LATERAL jsonb_array_elements_text(COALESCE(ct.conditions, '[]'::jsonb)) AS cond(indication)
    WHERE ct.molecule_id IS NOT NULL
    GROUP BY ct.molecule_id
),

-- Per-molecule sponsors: distinct lead_sponsor_name aggregated to JSONB array
sponsors_agg AS (
    SELECT
        ct.molecule_id,
        jsonb_agg(DISTINCT ct.lead_sponsor_name) FILTER (WHERE ct.lead_sponsor_name IS NOT NULL) AS sponsors
    FROM mol_silver.clinical_trials ct
    WHERE ct.molecule_id IS NOT NULL
    GROUP BY ct.molecule_id
),

-- Per-molecule safety summary from FAERS+SIDER aggregated adverse_events
safety_agg AS (
    SELECT
        ae.molecule_id,
        jsonb_build_object(
            'total_reports',   COALESCE(SUM(ae.report_count),  0),
            'serious_reports', COALESCE(SUM(ae.serious_count), 0),
            'death_reports',   COALESCE(SUM(ae.death_count),   0)
        ) AS safety_summary
    FROM mol_silver.adverse_events ae
    WHERE ae.molecule_id IS NOT NULL
    GROUP BY ae.molecule_id
)

SELECT
    mc.molecule_id,
    mc.inchi_key,
    mc.canonical_name,
    mc.therapeutic_areas,
    mc.mechanism_of_action,
    mc.development_status,
    mc.max_phase,

    COALESCE(ta.active_trials, 0)         AS active_trials,
    COALESCE(ta.phase_distribution, '{}'::jsonb) AS phase_distribution,
    COALESCE(ia.indications, '[]'::jsonb) AS indications,
    COALESCE(sa.sponsors,    '[]'::jsonb) AS sponsors,
    ta.latest_trial_start,
    COALESCE(ta.total_trials, 0)          AS total_trials,
    COALESCE(ta.sponsor_count, 0)         AS sponsor_count,
    COALESCE(safe.safety_summary, '{}'::jsonb) AS safety_summary,

    NOW() AS computed_at

FROM molecules_classified mc
LEFT JOIN trial_agg      ta   ON mc.molecule_id = ta.molecule_id
LEFT JOIN indications_agg ia  ON mc.molecule_id = ia.molecule_id
LEFT JOIN sponsors_agg   sa   ON mc.molecule_id = sa.molecule_id
LEFT JOIN safety_agg     safe ON mc.molecule_id = safe.molecule_id
WHERE mc.development_status IN ('phase_1', 'phase_2', 'phase_3', 'approved')
   OR ta.total_trials > 0
ORDER BY ta.active_trials DESC NULLS LAST, mc.max_phase DESC NULLS LAST

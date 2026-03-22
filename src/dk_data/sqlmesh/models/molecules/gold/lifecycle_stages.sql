-- SQLMesh Model: Gold Lifecycle Stages
-- Pre-computed lifecycle stage detection with evidence summary
-- Implements automatic stage detection based on evidence from all sources
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_gold.lifecycle_stages,
    kind FULL,
    cron '@daily',
    grain (molecule_id)
);

WITH molecule_base AS (
    SELECT
        m.molecule_id,
        m.inchi_key,
        m.canonical_name,
        m.max_phase
    FROM mol_silver.molecules m
    WHERE m.needs_review = FALSE
),

-- Clinical trial evidence
-- phases is JSONB in silver (e.g. ["Phase 3"]) — cast to TEXT for LIKE matching
-- overall_status is the correct column name (not status)
trial_evidence AS (
    SELECT
        molecule_id,
        MAX(CASE WHEN phases::TEXT LIKE '%4%' THEN 4
                 WHEN phases::TEXT LIKE '%3%' THEN 3
                 WHEN phases::TEXT LIKE '%2%' THEN 2
                 WHEN phases::TEXT LIKE '%1%' THEN 1
                 ELSE 0 END) AS max_trial_phase,
        COUNT(*) AS total_trials,
        COUNT(*) FILTER (WHERE overall_status IN ('Recruiting', 'Active, not recruiting', 'Enrolling by invitation')) AS active_trials,
        COUNT(*) FILTER (WHERE overall_status = 'Completed') AS completed_trials,
        bool_or(overall_status = 'Terminated' OR overall_status = 'Suspended') AS has_terminated_trials,
        MAX(start_date) AS latest_trial_start,
        MAX(completion_date) AS latest_trial_completion
    FROM mol_silver.clinical_trials
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Drug label evidence (FDA approval)
-- marketing_status doesn't exist in silver; use product_type instead
label_evidence AS (
    SELECT DISTINCT ON (molecule_id)
        molecule_id,
        TRUE AS has_fda_label,
        effective_date AS approval_date,
        product_type AS marketing_status,
        has_boxed_warning
    FROM mol_silver.drug_labels
    WHERE molecule_id IS NOT NULL
    ORDER BY molecule_id, effective_date DESC
),

-- Adverse event evidence (post-market surveillance)
-- adverse_events has individual report rows with boolean seriousness flags
adverse_evidence AS (
    SELECT
        molecule_id,
        COUNT(*) AS total_adverse_reports,
        MIN(receive_date) AS first_adverse_date,
        MAX(receipt_date) AS last_adverse_date,
        CASE WHEN COUNT(*) > 100 THEN TRUE ELSE FALSE END AS has_significant_adverse_data
    FROM mol_silver.adverse_events
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Patent evidence (ip_silver not yet populated — empty stub)
patent_evidence AS (
    SELECT
        NULL::UUID AS molecule_id,
        0 AS patent_count,
        NULL::DATE AS earliest_active_expiry,
        NULL::DATE AS latest_expiry,
        FALSE AS has_expired_patents
    WHERE FALSE
),

-- Publication evidence (ip_silver not yet populated — empty stub)
publication_evidence AS (
    SELECT
        NULL::UUID AS molecule_id,
        0 AS publication_count,
        NULL::DATE AS first_publication,
        NULL::DATE AS latest_publication
    WHERE FALSE
),

-- Bioactivity evidence (placeholder model — no molecule_id/target_id columns yet)
bioactivity_evidence AS (
    SELECT
        NULL::UUID AS molecule_id,
        0 AS bioactivity_count,
        0 AS targets_tested
    WHERE FALSE
),

-- Compute lifecycle stage
stage_detection AS (
    SELECT
        mb.molecule_id,
        mb.inchi_key,
        mb.canonical_name,
        mb.max_phase,

        -- Detect stage based on evidence hierarchy
        CASE
            -- Withdrawn: Has label + no recent adverse events + terminated status
            WHEN le.has_fda_label AND te.has_terminated_trials
                 AND ae.last_adverse_date < CURRENT_DATE - INTERVAL '2 years'
            THEN 'Withdrawn'

            -- Marketed: Has FDA label + significant FAERS data + >1 year since approval
            WHEN le.has_fda_label
                 AND ae.has_significant_adverse_data
                 AND le.approval_date < CURRENT_DATE - INTERVAL '1 year'
            THEN 'Marketed'

            -- Approved: Has FDA label
            WHEN le.has_fda_label
            THEN 'Approved'

            -- Phase 4: Has label + Phase 4 trial
            WHEN le.has_fda_label AND te.max_trial_phase = 4
            THEN 'Phase 4'

            -- Phase 3: Has completed or active Phase 3 trial
            WHEN te.max_trial_phase >= 3 AND te.active_trials > 0
            THEN 'Phase 3'

            -- Phase 2: Has completed or active Phase 2 trial
            WHEN te.max_trial_phase >= 2 AND te.active_trials > 0
            THEN 'Phase 2'

            -- Phase 1: Has completed or active Phase 1 trial
            WHEN te.max_trial_phase >= 1
            THEN 'Phase 1'

            -- Preclinical: Has bioactivity or patent data but no trials
            WHEN (be.bioactivity_count > 0 OR pe.patent_count > 0)
                 AND COALESCE(te.total_trials, 0) = 0
            THEN 'Preclinical'

            -- Discovery: Has publications but no other evidence
            WHEN pube.publication_count > 0
            THEN 'Discovery'

            ELSE 'Unknown'
        END AS detected_stage,

        -- Confidence score based on evidence strength
        CASE
            WHEN le.has_fda_label THEN 1.0
            WHEN te.completed_trials > 0 THEN 0.9
            WHEN te.active_trials > 0 THEN 0.8
            WHEN be.bioactivity_count > 5 THEN 0.7
            WHEN pube.publication_count > 0 THEN 0.5
            ELSE 0.3
        END AS stage_confidence,

        -- Evidence counts
        COALESCE(te.total_trials, 0) AS trial_count,
        COALESCE(te.active_trials, 0) AS active_trial_count,
        COALESCE(te.completed_trials, 0) AS completed_trial_count,
        te.max_trial_phase,
        le.has_fda_label,
        le.approval_date,
        COALESCE(ae.total_adverse_reports, 0) AS adverse_report_count,
        COALESCE(pe.patent_count, 0) AS patent_count,
        pe.earliest_active_expiry AS next_patent_expiry,
        COALESCE(pube.publication_count, 0) AS publication_count,
        COALESCE(be.bioactivity_count, 0) AS bioactivity_count,

        -- Evidence summary JSON
        jsonb_build_object(
            'trials', jsonb_build_object(
                'total', COALESCE(te.total_trials, 0),
                'active', COALESCE(te.active_trials, 0),
                'completed', COALESCE(te.completed_trials, 0),
                'max_phase', te.max_trial_phase,
                'latest_start', te.latest_trial_start
            ),
            'regulatory', jsonb_build_object(
                'has_fda_label', COALESCE(le.has_fda_label, FALSE),
                'approval_date', le.approval_date,
                'marketing_status', le.marketing_status,
                'has_boxed_warning', COALESCE(le.has_boxed_warning, FALSE)
            ),
            'safety', jsonb_build_object(
                'total_reports', COALESCE(ae.total_adverse_reports, 0),
                'first_report', ae.first_adverse_date,
                'last_report', ae.last_adverse_date
            ),
            'ip', jsonb_build_object(
                'patent_count', COALESCE(pe.patent_count, 0),
                'next_expiry', pe.earliest_active_expiry,
                'has_expired', COALESCE(pe.has_expired_patents, FALSE)
            ),
            'research', jsonb_build_object(
                'publications', COALESCE(pube.publication_count, 0),
                'bioactivity_assays', COALESCE(be.bioactivity_count, 0),
                'targets_tested', COALESCE(be.targets_tested, 0)
            )
        ) AS evidence_summary

    FROM molecule_base mb
    LEFT JOIN trial_evidence te ON mb.molecule_id = te.molecule_id
    LEFT JOIN label_evidence le ON mb.molecule_id = le.molecule_id
    LEFT JOIN adverse_evidence ae ON mb.molecule_id = ae.molecule_id
    LEFT JOIN patent_evidence pe ON mb.molecule_id = pe.molecule_id
    LEFT JOIN publication_evidence pube ON mb.molecule_id = pube.molecule_id
    LEFT JOIN bioactivity_evidence be ON mb.molecule_id = be.molecule_id
)

SELECT
    molecule_id,
    inchi_key,
    canonical_name,
    max_phase AS source_max_phase,
    detected_stage,
    stage_confidence,

    -- Stage ordinal for sorting/comparison
    CASE detected_stage
        WHEN 'Withdrawn' THEN 8
        WHEN 'Marketed' THEN 7
        WHEN 'Approved' THEN 6
        WHEN 'Phase 4' THEN 5
        WHEN 'Phase 3' THEN 4
        WHEN 'Phase 2' THEN 3
        WHEN 'Phase 1' THEN 2
        WHEN 'Preclinical' THEN 1
        WHEN 'Discovery' THEN 0
        ELSE -1
    END AS stage_ordinal,

    -- Evidence counts
    trial_count,
    active_trial_count,
    completed_trial_count,
    max_trial_phase,
    COALESCE(has_fda_label, FALSE) AS has_fda_label,
    approval_date,
    adverse_report_count,
    patent_count,
    next_patent_expiry,
    publication_count,
    bioactivity_count,

    -- Detailed evidence summary
    evidence_summary,

    -- Stage status (confirmed for all; will add change detection when development_status is available)
    'confirmed' AS stage_status,

    NOW() AS computed_at

FROM stage_detection
ORDER BY stage_ordinal DESC, stage_confidence DESC

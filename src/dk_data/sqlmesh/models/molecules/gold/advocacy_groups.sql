-- SQLMesh Model: Gold Advocacy Groups
-- Aggregated patient/disease advocacy organizations from news signals
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_gold.advocacy_groups,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (organization_name))
    ),
    grain (group_id)
);

-- mol_silver.news_signals is populated by ip_silver pipeline (not yet run).
-- Return empty result set with correct schema until ip_silver runs.
SELECT
    gen_random_uuid() AS group_id,
    NULL::TEXT AS organization_name,
    NULL::TEXT AS disease_focus,
    NULL::TEXT AS size_estimate,
    NULL::TEXT[] AS activities,
    NULL::TEXT AS indication,
    0 AS signal_count,
    NULL::DATE AS last_activity_date,
    NOW() AS created_at,
    NOW() AS updated_at
WHERE FALSE;

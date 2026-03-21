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

-- Derive advocacy groups from news signals that mention organizations
WITH org_signals AS (
    SELECT
        ns.source_name AS organization_name,
        ns.therapeutic_area AS disease_focus,
        COUNT(*) AS signal_count,
        ARRAY_AGG(DISTINCT ns.signal_type) AS activities,
        MAX(ns.pub_date) AS last_activity_date,
        -- Size estimate based on signal volume
        CASE
            WHEN COUNT(*) >= 50 THEN 'Large'
            WHEN COUNT(*) >= 10 THEN 'Medium'
            ELSE 'Small'
        END AS size_estimate
    FROM mol_silver.news_signals ns
    WHERE ns.source_name IS NOT NULL
    GROUP BY ns.source_name, ns.therapeutic_area
),

-- Extract indication from drug mentions where available
with_indication AS (
    SELECT
        o.*,
        COALESCE(o.disease_focus, 'General') AS indication
    FROM org_signals o
)

SELECT
    gen_random_uuid() AS group_id,
    organization_name,
    disease_focus,
    size_estimate,
    activities,
    indication,
    signal_count,
    last_activity_date,
    NOW() AS created_at,
    NOW() AS updated_at
FROM with_indication;

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
        -- Aggregate mentioned drug names for molecule linkage
        ARRAY_AGG(DISTINCT ns.drug_mentions) FILTER (WHERE ns.drug_mentions IS NOT NULL) AS drug_mentions_list,
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

-- Link to mol_silver.molecules to count distinct molecules covered by each org
-- and surface top molecules by mention frequency
molecule_coverage AS (
    SELECT
        os.organization_name,
        COUNT(DISTINCT m.molecule_id)                           AS molecule_count,
        ARRAY_AGG(DISTINCT m.canonical_name ORDER BY m.canonical_name)
            FILTER (WHERE m.canonical_name IS NOT NULL)         AS covered_molecules
    FROM org_signals os
    -- drug_mentions_list holds raw comma-separated strings (e.g. "ibuprofen, aspirin").
    -- Unnest the array then split each element so we match individual drug names.
    CROSS JOIN LATERAL unnest(os.drug_mentions_list) AS raw_entry
    CROSS JOIN LATERAL unnest(string_to_array(TRIM(raw_entry), ', ')) AS dm_entry
    JOIN mol_silver.molecules m
        ON LOWER(m.canonical_name) = LOWER(TRIM(dm_entry))
    GROUP BY os.organization_name
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
    wi.organization_name,
    wi.disease_focus,
    wi.size_estimate,
    wi.activities,
    wi.indication,
    wi.signal_count,
    wi.last_activity_date,
    COALESCE(mc.molecule_count, 0)  AS molecule_count,
    mc.covered_molecules,
    NOW() AS created_at,
    NOW() AS updated_at
FROM with_indication wi
LEFT JOIN molecule_coverage mc ON wi.organization_name = mc.organization_name;

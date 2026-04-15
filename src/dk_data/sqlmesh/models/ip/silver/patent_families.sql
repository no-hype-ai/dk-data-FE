-- T069: ip_silver.patent_families — FULL model
-- One row per family_id aggregating member patents from both USPTO and EPO.
-- Family ID comes from ip_bronze.epo_patents.family_id (always present for EPO)
-- and ip_bronze.uspto_patents.family_id (T055 expansion).
-- Part of: 006-claims-engine-data-gaps (Item 28)

MODEL (
    name ip_silver.patent_families,
    kind FULL,
    cron '@weekly',
    grain (family_id)
);

WITH family_members AS (
    -- USPTO patents with family_id
    SELECT
        u.family_id,
        u.patent_number,
        'US' AS jurisdiction,
        u.filing_date::date AS filing_date,
        u.patent_date::date AS grant_date
    FROM ip_bronze.uspto_patents u
    WHERE u.family_id IS NOT NULL

    UNION ALL

    -- EPO patents with family_id
    SELECT
        e.family_id,
        e.patent_number,
        'EP' AS jurisdiction,
        e.filing_date::date AS filing_date,
        e.grant_date::date AS grant_date
    FROM ip_bronze.epo_patents e
    WHERE e.family_id IS NOT NULL
),

aggregated AS (
    SELECT
        family_id,
        COUNT(*) AS member_count,
        jsonb_agg(
            jsonb_build_object(
                'patent_number', patent_number,
                'jurisdiction', jurisdiction,
                'filing_date', filing_date,
                'grant_date', grant_date
            )
            ORDER BY filing_date NULLS LAST
        ) AS member_patents
    FROM family_members
    GROUP BY family_id
)

SELECT
    family_id,
    member_count,
    member_patents,
    NOW() AS last_updated_at
FROM aggregated

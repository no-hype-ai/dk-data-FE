-- SQLMesh Model: Gold KOL Network
-- Co-authorship network edges between researchers
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_gold.kol_network,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source_researcher_id, target_researcher_id)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (source_researcher_id, target_researcher_id))
    ),
    grain (source_researcher_id, target_researcher_id),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- Build co-authorship edges by self-joining publications on shared DOIs
-- Each researcher pair that has co-authored at least one publication produces an edge

WITH author_publications AS (
    -- Map researchers to their publications via name matching.
    -- Word-boundary regex (\m/\M) prevents short surnames (e.g. "Lee") from matching
    -- mid-word in author display names. Length guard ≥4 reduces false positives.
    SELECT DISTINCT
        r.id AS researcher_id,
        p.doi
    FROM mol_silver.researchers r
    JOIN mol_silver.publications p
        ON LENGTH(r.family_name) >= 4
       AND p.first_author_name ~* ('\m' || r.family_name || '\M')
    WHERE p.doi IS NOT NULL
      AND r.id IS NOT NULL
),

-- Self-join to find co-author pairs
co_author_pairs AS (
    SELECT
        ap1.researcher_id AS source_researcher_id,
        ap2.researcher_id AS target_researcher_id,
        COUNT(DISTINCT ap1.doi) AS shared_publications
    FROM author_publications ap1
    JOIN author_publications ap2
        ON ap1.doi = ap2.doi
        AND ap1.researcher_id < ap2.researcher_id  -- Avoid duplicates and self-joins
    GROUP BY ap1.researcher_id, ap2.researcher_id
)

SELECT
    gen_random_uuid() AS id,
    source_researcher_id,
    target_researcher_id,
    shared_publications,
    'co_author' AS connection_type,
    NOW() AS created_at,
    NOW() AS updated_at
FROM co_author_pairs
WHERE shared_publications >= 1;

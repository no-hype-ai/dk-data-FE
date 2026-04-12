-- SQLMesh Model: Silver CMS Coverage Policies
-- Typed pass-through of Medicare coverage decisions from mol_bronze.cms_coverage.
-- No direct drug identifier in source data — molecule linkage attempted via
-- title keyword match against mol_silver.molecule_names (low confidence, optional).
-- LATERAL subquery returns at most one alias match per coverage row (avoids O(N*M) cross-join).
-- Prefers the highest-confidence alias (longest display_name among matches, then LIMIT 1).
-- Consumers: competitive landscape, market access analysis.
-- Part of: issue #172 H2, #173 H2, #186 H3

MODEL (
    name mol_silver.cms_coverage,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key coverage_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (coverage_id, source))
    ),
    grain coverage_id
);

SELECT DISTINCT ON (b.coverage_id)
    gen_random_uuid()               AS id,
    b.coverage_id,
    b.endpoint,
    b.title,
    b.decision,
    b.decision_date,
    b.last_updated_date,
    b.source_number,
    b.topic,

    -- Attempt molecule linkage via word-boundary regex match on coverage title.
    -- LATERAL + LIMIT 1 returns at most one match per row, avoiding O(N*M) cross-join.
    -- \m/\M anchors prevent short common words (iron, zinc) from matching mid-word.
    -- NULL when no alias matches — not all coverage decisions name a specific drug.
    alias_match.molecule_id,

    b.source,
    b.ingested_at,
    b.source_updated_at,
    NOW()                           AS created_at

FROM mol_bronze.cms_coverage b
LEFT JOIN LATERAL (
    SELECT ma.molecule_id
    FROM mol_silver.molecule_names ma
    WHERE b.title IS NOT NULL
      AND b.title ~* ('\m' || ma.display_name || '\M')
      AND LENGTH(ma.display_name) >= 4
    ORDER BY LENGTH(ma.display_name) DESC
    LIMIT 1
) alias_match ON TRUE
WHERE b.coverage_id IS NOT NULL
ORDER BY b.coverage_id, b.source_updated_at DESC NULLS LAST

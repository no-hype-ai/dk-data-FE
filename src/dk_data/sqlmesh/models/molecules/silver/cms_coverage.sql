-- SQLMesh Model: Silver CMS Coverage Policies
-- Typed pass-through of Medicare coverage decisions from mol_bronze.cms_coverage.
-- No direct drug identifier in source data — molecule linkage attempted via
-- title keyword match against mol_silver.molecule_aliases (low confidence, optional).
-- DISTINCT ON (coverage_id) applied to prevent fan-out when multiple aliases
-- match the same coverage title. Prefers rows with a non-null molecule_id.
-- Consumers: competitive landscape, market access analysis.
-- Part of: issue #172 H2, #173 H2

MODEL (
    name mol_silver.cms_coverage,
    kind FULL,
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
    -- \m/\M anchors prevent short common words (iron, zinc) from matching mid-word.
    -- NULL when no alias matches — not all coverage decisions name a specific drug.
    -- DISTINCT ON above ensures one row per coverage_id; ORDER BY prefers non-null molecule_id
    -- when multiple aliases match the same title.
    ma.molecule_id,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM mol_bronze.cms_coverage b
LEFT JOIN mol_silver.molecule_aliases ma
       ON b.title IS NOT NULL
      AND b.title ~* ('\m' || ma.alias_name || '\M')
      AND LENGTH(ma.alias_name) >= 4
WHERE b.coverage_id IS NOT NULL
ORDER BY b.coverage_id, ma.molecule_id NULLS LAST

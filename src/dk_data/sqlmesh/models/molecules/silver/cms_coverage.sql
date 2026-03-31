-- SQLMesh Model: Silver CMS Coverage Policies
-- Typed pass-through of Medicare coverage decisions from mol_bronze.cms_coverage.
-- No direct drug identifier in source data — molecule linkage attempted via
-- title keyword match against mol_silver.molecule_aliases (low confidence, optional).
-- Consumers: competitive landscape, market access analysis.
-- Part of: issue #172 H2

MODEL (
    name mol_silver.cms_coverage,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (coverage_id, source))
    ),
    grain coverage_id
);

SELECT
    gen_random_uuid()               AS id,
    b.coverage_id,
    b.endpoint,
    b.title,
    b.decision,
    b.decision_date,
    b.last_updated_date,
    b.source_number,
    b.topic,

    -- Attempt molecule linkage via alias match on coverage title.
    -- NULL when no alias matches — not all coverage decisions name a specific drug.
    ma.molecule_id,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM mol_bronze.cms_coverage b
LEFT JOIN mol_silver.molecule_aliases ma
       ON b.title IS NOT NULL
      AND LOWER(b.title) LIKE '%' || LOWER(ma.alias_name) || '%'
      AND LENGTH(ma.alias_name) >= 4
WHERE b.coverage_id IS NOT NULL

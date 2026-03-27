-- SQLMesh Model: Silver ClinicalTrials.gov Indication Statistics
-- Promotes mol_bronze.ct_gov_indication_stats into mol_silver.ct_gov_indication_stats.
-- Records per-indication trial counts from ClinicalTrials.gov v2 totalCount queries.
-- Entity linking: condition_query → mol_silver.molecules canonical_name or alias.

MODEL (
    name mol_silver.ct_gov_indication_stats,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key condition_query
    ),
    cron '@monthly',
    audits (
        not_null(columns := (condition_query))
    ),
    grain condition_query
);

SELECT
    gen_random_uuid()                                   AS id,
    COALESCE(m_exact.molecule_id, m_alias.molecule_id) AS molecule_id,
    b.condition_query,
    b.total_count                                       AS trial_count,
    'ct_gov_indication_stats'                           AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM mol_bronze.ct_gov_indication_stats b
-- Link via exact canonical name match
LEFT JOIN mol_silver.molecules m_exact
       ON b.condition_query IS NOT NULL
      AND LOWER(m_exact.canonical_name) = LOWER(b.condition_query)
-- Fallback: alias match
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_exact.molecule_id IS NULL
      AND b.condition_query IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.condition_query, '[^a-zA-Z0-9]', '', 'g'))
          = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
WHERE b.condition_query IS NOT NULL
  AND b.total_count IS NOT NULL;

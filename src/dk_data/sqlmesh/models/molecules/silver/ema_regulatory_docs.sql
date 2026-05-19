-- SQLMesh Model: mol_silver.ema_regulatory_docs
-- EMA regulatory document records (EPARs, PARs, decision documents) with molecule linkage.
-- Distinct from mol_silver.ema_regulatory (which promotes mol_bronze.ema product approvals);
-- this model promotes mol_bronze.ema_regulatory document-level records.
-- Grain: document_id
--
-- Linkage strategy (tiered):
--   Tier 1: active_substance → mol_silver.molecules (canonical_name exact match)
--   Tier 2: active_substance → mol_silver.molecule_names (normalized, LATERAL LIMIT 1)
--   Tier 3: first token of active_substance → molecule_aliases (handles multi-word INN variants)

MODEL (
    name mol_silver.ema_regulatory_docs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key document_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (document_id))
    ),
    grain document_id
);

SELECT DISTINCT ON (b.document_id)
    gen_random_uuid()                       AS id,
    b.document_id,
    b.document_type,
    b.product_name,
    b.active_substance,
    b.therapeutic_area,
    b.decision_date,
    b.decision_type,
    b.document_url,
    b.summary,

    -- Molecule linkage
    COALESCE(m_exact.molecule_id, mol_alias.molecule_id) AS molecule_id,

    -- Link quality
    CASE
        WHEN m_exact.molecule_id IS NOT NULL THEN 'canonical_exact'
        WHEN mol_alias.molecule_id IS NOT NULL THEN 'alias_match'
        ELSE 'unlinked'
    END                                     AS link_strategy,

    -- Source metadata
    b._source_file,
    b._source_hash,

    b.source,
    b.source_updated_at,
    NOW()                                   AS created_at

FROM mol_bronze.ema_regulatory b

-- Tier 1: exact canonical_name match on active_substance
LEFT JOIN mol_silver.molecules m_exact
       ON b.active_substance IS NOT NULL
      AND LOWER(m_exact.canonical_name) = LOWER(b.active_substance)

-- Tier 2+3: alias match — full normalized name, then first-token fallback
LEFT JOIN LATERAL (
    SELECT ma.molecule_id
    FROM mol_silver.molecule_names ma
    WHERE m_exact.molecule_id IS NULL
      AND b.active_substance IS NOT NULL
      AND (
          LOWER(REGEXP_REPLACE(b.active_substance, '[^a-zA-Z0-9]', '', 'g')) = ma.normalized_name
          OR (
              LENGTH(SPLIT_PART(b.active_substance, ' ', 1)) >= 4
              AND LOWER(REGEXP_REPLACE(
                      SPLIT_PART(b.active_substance, ' ', 1),
                      '[^a-zA-Z0-9]', '', 'g'
                  )) = ma.normalized_name
          )
      )
    ORDER BY ma.molecule_id
    LIMIT 1
) mol_alias ON TRUE

WHERE b.document_id IS NOT NULL
ORDER BY b.document_id, m_exact.molecule_id NULLS LAST, mol_alias.molecule_id NULLS LAST

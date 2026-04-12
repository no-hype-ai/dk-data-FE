-- SQLMesh Model: Silver Trademark Status Changes
-- Enriches ip_bronze.trademark_status_history with molecule linkage and
-- full trademark context from ip_silver.trademarks.
--
-- Grain: (trademark_identifier, source, changed_at)
-- Dedup: INCREMENTAL_BY_UNIQUE_KEY on the three-column grain prevents duplicate
--   inserts if the daily bronze job runs multiple times.
--
-- Molecule linkage: trademarks are linked to molecules via mark_name → canonical_name
--   (exact) and mark_name → alias (fallback). Unlinked status changes are retained
--   with molecule_id = NULL for audit completeness.
--
-- Ref: issue #171 M5
-- Migrated from mol_silver → ip_silver by 001-silver-medallion-rebuild (FR-006e)

MODEL (
    name ip_silver.trademark_status_changes,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (trademark_identifier, source, changed_at)
    ),
    cron '@daily',
    audits (
        not_null(columns := (trademark_identifier, source, new_status, changed_at))
    ),
    grain (trademark_identifier, source, changed_at)
);

SELECT DISTINCT ON (h.trademark_identifier, h.source, h.changed_at)
    h.trademark_identifier,
    h.source,
    h.old_status,
    h.new_status,
    h.transition_type,
    h.changed_at,

    -- Full trademark context at the time of the status snapshot
    t.mark_name,
    t.mark_type,
    t.owner_name,
    t.filing_date,
    t.registration_date,
    t.nice_classes,
    t.goods_and_services,
    t.is_pharma_related,

    -- Molecule linkage via mark_name → canonical name (exact) → alias (fallback)
    COALESCE(m_exact.molecule_id, m_alias.molecule_id)  AS molecule_id,

    h.source_updated_at,
    NOW()                                               AS created_at

FROM ip_bronze.trademark_status_history h

-- Join current trademark snapshot for context
LEFT JOIN ip_silver.trademarks t
       ON t.trademark_identifier = h.trademark_identifier
      AND t.source               = h.source

-- Tier 1: exact canonical name match
LEFT JOIN mol_silver.molecules m_exact
       ON t.mark_name IS NOT NULL
      AND LOWER(TRIM(t.mark_name)) = LOWER(TRIM(m_exact.canonical_name))

-- Tier 2: alias match when no canonical match
LEFT JOIN mol_silver.molecule_names ma
       ON m_exact.molecule_id IS NULL
      AND t.mark_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(t.mark_name, '[^a-zA-Z0-9]', '', 'g'))
          = ma.normalized_name
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
ORDER BY h.trademark_identifier, h.source, h.changed_at, h.source_updated_at DESC NULLS LAST;

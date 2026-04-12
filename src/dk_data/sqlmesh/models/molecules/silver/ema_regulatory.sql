-- SQLMesh Model: mol_silver.ema_regulatory
-- EMA regulatory decisions linked to mol_silver.molecules
--
-- Feature: 019-cms-puf-platform-reconciliation
-- Task: T024
--
-- Joins mol_bronze.ema decisions to mol_silver.molecules via canonical_name →
-- active_substance matching, producing a molecule-centric regulatory view.
-- Distinct from mol_silver.regulatory_decisions (which merges EMA + HTA generically);
-- this model provides EMA-specific regulatory status per molecule_id.

MODEL (
    name mol_silver.ema_regulatory,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, product_number)
    ),
    cron '@weekly',
    grain (molecule_id, product_number),
    audits (
        not_null(columns := (product_number, authorization_status))
    ),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT
    COALESCE(m.molecule_id, m_alias.molecule_id) AS molecule_id,
    e.product_number,
    e.product_name,
    e.active_substance,
    e.inn,
    e.atc_code,
    e.marketing_authorization_holder,
    e.authorization_status,
    e.authorization_date,
    e.revision_date,
    e.medicine_type,
    e.therapeutic_area,
    e.pharmacotherapeutic_group,
    e.epar_url,
    e.summary_url,

    -- Link quality: how the molecule was matched
    CASE
        WHEN m.molecule_id IS NOT NULL AND LOWER(m.canonical_name) = LOWER(e.active_substance) THEN 'active_substance_exact'
        WHEN m.molecule_id IS NOT NULL AND LOWER(m.canonical_name) = LOWER(e.inn)              THEN 'inn_exact'
        WHEN m.molecule_id IS NOT NULL                                                          THEN 'active_substance_partial'
        WHEN m_alias.molecule_id IS NOT NULL                                                    THEN 'alias_match'
        ELSE 'unlinked'
    END AS link_strategy,

    e.source,
    e.source_updated_at,
    e.ingested_at

FROM mol_bronze.ema AS e
-- Strategy 1: canonical_name = active_substance OR inn (deduplicated via LATERAL)
LEFT JOIN LATERAL (
    SELECT DISTINCT ON (1)
        m.molecule_id,
        CASE
            WHEN LOWER(m.canonical_name) = LOWER(e.active_substance) THEN 1
            ELSE 2
        END AS match_priority
    FROM mol_silver.molecules m
    WHERE LOWER(m.canonical_name) = LOWER(e.active_substance)
       OR LOWER(m.canonical_name) = LOWER(e.inn)
    ORDER BY 1, match_priority
    LIMIT 1
) mol_match ON TRUE
LEFT JOIN mol_silver.molecules m ON m.molecule_id = mol_match.molecule_id
-- Strategy 2: molecule_aliases on normalized active_substance
--   Catches EMA variants like "bevacizumab alfa" → first token "bevacizumab" → alias match
-- Strategy 2: alias match — use subquery with LIMIT 1 to prevent fan-out when
-- multiple aliases (or the same alias for different molecules) match active_substance.
LEFT JOIN LATERAL (
    SELECT ma2.molecule_id
    FROM mol_silver.molecule_names ma2
    WHERE m.molecule_id IS NULL
      AND e.active_substance IS NOT NULL
      AND (
          LOWER(REGEXP_REPLACE(e.active_substance, '[^a-zA-Z0-9]', '', 'g')) = ma2.normalized_name
          OR
          (LENGTH(SPLIT_PART(e.active_substance, ' ', 1)) >= 4
           AND LOWER(REGEXP_REPLACE(
                   SPLIT_PART(e.active_substance, ' ', 1),
                   '[^a-zA-Z0-9]', '', 'g'
               )) = ma2.normalized_name)
      )
    ORDER BY ma2.molecule_id
    LIMIT 1
) alias_match ON TRUE
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = alias_match.molecule_id
      AND m.molecule_id IS NULL

WHERE e.product_number IS NOT NULL
  AND e.authorization_status IS NOT NULL

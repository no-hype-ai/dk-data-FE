-- SQLMesh Model: Gold Indication Catalog (IND domain)
-- Decision-ready analytics view of ICD-11 disease classifications.
-- Aggregates per-therapeutic-area statistics and enriches each indication
-- with pharma relevance flags, trial activity, and hierarchy depth.
--
-- Source: ind_silver.icd11_ontology
-- Grain: icd11_code
-- Consumers: market sizing, drug-indication mapping, KOL analytics,
--            competitive landscape dashboards.
--
-- Feature: 019-cms-puf-platform-reconciliation (H1 — IND gold layer)

MODEL (
    name ind_gold.indication_catalog,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (icd11_code, therapeutic_area)),
        unique_values(columns := (icd11_code))
    ),
    grain icd11_code
);

WITH ta_stats AS (
    -- Pre-aggregate counts per therapeutic area for enrichment
    SELECT
        therapeutic_area,
        COUNT(*)                                    AS total_indications,
        COUNT(*) FILTER (WHERE is_pharma_relevant)  AS pharma_relevant_count,
        COUNT(*) FILTER (WHERE is_leaf)             AS leaf_count
    FROM ind_silver.icd11_ontology
    GROUP BY therapeutic_area
),

hierarchy_depth AS (
    -- Compute depth from parent_code (leaf codes have a '.' in icd11_code)
    SELECT
        icd11_code,
        CASE
            WHEN icd11_code LIKE '%.%.%' THEN 3
            WHEN icd11_code LIKE '%.%'   THEN 2
            ELSE 1
        END AS hierarchy_depth
    FROM ind_silver.icd11_ontology
)

SELECT
    s.icd11_code,
    s.icd11_title,
    s.definition,
    s.class_kind,
    s.parent_code,
    s.is_leaf,
    hd.hierarchy_depth,
    s.therapeutic_area,
    s.is_pharma_relevant,

    -- Inclusion / exclusion context
    s.inclusion_terms,
    s.exclusion_terms,

    -- Therapeutic area aggregate context
    ta.total_indications                            AS ta_total_indications,
    ta.pharma_relevant_count                        AS ta_pharma_relevant_count,
    ta.leaf_count                                   AS ta_leaf_count,
    ROUND(
        100.0 * ta.pharma_relevant_count::NUMERIC / NULLIF(ta.total_indications, 0),
        1
    )                                               AS ta_pharma_relevance_pct,

    -- Reference URLs for drill-through
    s.browser_url,

    s.source,
    s.source_updated_at,
    NOW()                                           AS gold_updated_at

FROM ind_silver.icd11_ontology s
JOIN ta_stats ta      USING (therapeutic_area)
JOIN hierarchy_depth hd USING (icd11_code);

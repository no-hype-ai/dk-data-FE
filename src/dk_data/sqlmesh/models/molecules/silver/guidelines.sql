-- SQLMesh Model: Silver Treatment Guidelines
-- Enriched guidelines with molecule and condition crosswalks
-- Part of: 006-claims-engine-data-gaps (Item 8, T050)

MODEL (
    name mol_silver.guidelines,
    kind FULL,
    cron '@weekly',
    grain (raw_source_id)
);

SELECT
    g.raw_source_id,
    g.body,
    g.title,
    g.publication_date,
    g.version,
    g.indication_icd11,
    g.indication_name,
    g.source_url,
    g.full_text,
    g.sections,
    g.recommendations,

    -- Molecule crosswalk: LEFT JOIN on indication_name ~ molecule canonical name
    m.molecule_id,

    -- Condition crosswalk: match indication_icd11 to ind_silver.conditions
    c.condition_id,
    c.condition_name AS resolved_condition_name,

    g.ingested_at,
    NOW() AS last_updated_at

FROM mol_bronze.guidelines g

LEFT JOIN mol_silver.molecules m
    ON LOWER(g.indication_name) = LOWER(m.canonical_name)

LEFT JOIN ind_silver.conditions c
    ON g.indication_icd11 IS NOT NULL
   AND c.icd11_code = g.indication_icd11

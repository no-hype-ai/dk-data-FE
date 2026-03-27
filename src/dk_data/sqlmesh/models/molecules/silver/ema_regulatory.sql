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
    kind FULL,
    cron '@weekly',
    grain (molecule_id, product_number),
    audits (
        not_null(columns := (product_number, authorization_status))
    )
);

SELECT
    m.molecule_id,
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
        WHEN LOWER(m.canonical_name) = LOWER(e.active_substance) THEN 'active_substance_exact'
        WHEN LOWER(m.canonical_name) = LOWER(e.inn) THEN 'inn_exact'
        WHEN LOWER(m.canonical_name) LIKE '%' || LOWER(e.active_substance) || '%' THEN 'active_substance_partial'
        ELSE 'unlinked'
    END AS link_strategy,

    e.ingested_at

FROM mol_bronze.ema AS e
LEFT JOIN mol_silver.molecules AS m
    ON LOWER(m.canonical_name) = LOWER(e.active_substance)
    OR LOWER(m.canonical_name) = LOWER(e.inn)

WHERE e.product_number IS NOT NULL
  AND e.authorization_status IS NOT NULL

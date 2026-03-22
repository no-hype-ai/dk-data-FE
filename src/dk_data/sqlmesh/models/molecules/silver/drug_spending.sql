-- SQLMesh Model: Silver Drug Spending
-- Promotes CMS Medicare Part B/D spending from mol_bronze.cms_medicare_spending
-- into mol_silver.drug_spending with molecule-level linkage.
-- molecule_id is NULL here — entity linking fills it after promotion.
-- Part of: Tier 4 gap fix — was blocked by enabled=false cron + missing silver model

MODEL (
    name mol_silver.drug_spending,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (brand_name, generic_name, program, year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (generic_name, program, year))
    ),
    grain (brand_name, generic_name, program, year)
);

SELECT
    gen_random_uuid()                   AS spending_id,
    NULL::UUID                          AS molecule_id,  -- entity linking fills this
    b.brand_name,
    b.generic_name,
    b.program,
    b.year,
    b.total_claims,
    b.total_beneficiaries,
    b.total_spending,
    b.avg_cost_per_claim,
    b.avg_cost_per_day,
    b.avg_cost_per_beneficiary,
    b.total_supply_days,
    'cms_medicare'                      AS source,
    b.ingested_at                       AS created_at

FROM mol_bronze.cms_medicare_spending b
WHERE b.processed_to_silver = FALSE
  AND b.generic_name IS NOT NULL
  AND b.year IS NOT NULL;

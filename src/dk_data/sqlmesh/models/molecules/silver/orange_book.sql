-- SQLMesh Model: Silver Orange Book (FDA approved drug products)
-- Promotes mol_bronze.orange_book to silver, linking to mol_silver.molecules.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Grain: (application_number, product_number, _file_type)
-- Source: mol_bronze.orange_book (from mol_raw.orange_book via OrangeBookFetcher)
-- Covers products, patents, and exclusivity records (distinguished by _file_type).

MODEL (
    name mol_silver.orange_book,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (application_number, _file_type))
    ),
    grain (application_number, product_number, _file_type)
);

SELECT
    b.application_number,
    b.product_number,
    b.ingredient                        AS active_ingredient,
    b.trade_name,
    b.applicant,
    b.applicant_full_name,
    b.strength,
    b.df_route,
    b.approval_date,
    b.te_code,
    b.rld,
    b.rs,
    b.type                              AS product_type,
    b._file_type,
    m.molecule_id,
    b.ingested_at                       AS _ingested_at,
    CURRENT_TIMESTAMP                   AS _silver_updated_at
FROM mol_bronze.orange_book AS b
LEFT JOIN mol_silver.molecules AS m
    ON LOWER(TRIM(b.ingredient)) = LOWER(TRIM(m.canonical_name))
WHERE b.application_number IS NOT NULL
  AND b._file_type IS NOT NULL

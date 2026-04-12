-- SQLMesh Model: Silver Purple Book (FDA biologics / biosimilars)
-- Column-retention silver pass-through (FR-001) for mol_bronze.purple_book.
-- Carries forward every non-system bronze column and resolves product_id via
-- mol_silver.drug_products using the deterministic BLA-keyed hash. is_biosimilar
-- and reference_product_id are exposed via the resolved hub row, not duplicated here.
--
-- Feature: 001-silver-medallion-rebuild (Gap 9 — biosimilar↔reference linkage)
-- Grain:   (bla_number, product_number)

MODEL (
    name mol_silver.purple_book,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (bla_number, product_number)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bla_number))
    ),
    grain (bla_number, product_number)
);

SELECT
    b.bla_number,
    b.product_number,
    b.applicant,
    b.brand_name,
    b.generic_name,
    b.license_type,
    b.dosage_form,
    b.strength,
    b.presentation,
    b.route,
    b.status,
    b.center,
    b.is_biosimilar,
    b.is_interchangeable,
    b.reference_product_name,
    b.reference_product_brand,
    b.approval_date,
    b.first_licensure_date,
    b.orphan_exclusivity_end,
    b.exclusivity_expiry_date,
    b.interchangeable_exclusivity_end,
    b.ref_product_exclusivity_end,
    b.interchangeable_approval_date,
    b.has_patent_list,

    -- Hub linkage: deterministic md5 over the same business key used by drug_products.
    ('x' || substr(md5('bla:' || b.bla_number || ':' || COALESCE(b.product_number, '0')), 1, 16))::bit(64)::bigint
        AS product_id,

    b.source,
    b.source_updated_at,
    b.ingested_at,
    CURRENT_TIMESTAMP                   AS _silver_updated_at
FROM mol_bronze.purple_book AS b
WHERE b.bla_number IS NOT NULL

-- T033: mol_silver.drug_products — drug product hub (SCD/SBD level — FR-012)
-- RxCUI is at TTY in (SCD, SBD, GPCK, BPCK) only. NDC lives in drug_product_identifiers.
-- PK is deterministic bigint from hash of primary business key.

MODEL (
    name mol_silver.drug_products,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key product_id
    ),
    grain product_id
);

WITH fda_products AS (
    SELECT
        ('x' || substr(md5(COALESCE(rxcui, 'fda:' || LOWER(COALESCE(nonproprietary_name, proprietary_name, application_number || ':' || product_number)))), 1, 16))::bit(64)::bigint AS product_id,
        NULLIF(rxcui, '')                                                        AS rxcui,
        NULLIF(application_number, '')                                           AS application_number,
        NULLIF(product_number, '')                                               AS application_product_number,
        NULL::text                                                               AS bla_number,
        NULL::text                                                               AS bla_product_number,
        NULL::text                                                               AS ema_product_number,
        NULL::text                                                               AS cvx_code,
        NULLIF(proprietary_name, '')                                             AS brand_name,
        NULLIF(nonproprietary_name, '')                                          AS generic_name,
        NULLIF(dosage_form, '')                                                  AS dosage_form,
        NULLIF(route, '')                                                        AS route,
        NULL::numeric                                                            AS strength_normalized_mg,
        FALSE                                                                    AS is_combination,
        FALSE                                                                    AS is_biologic,
        FALSE                                                                    AS is_biosimilar,
        NULL::bigint                                                             AS reference_product_id,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.fda_drugs
    WHERE COALESCE(nonproprietary_name, proprietary_name, application_number) IS NOT NULL
),

rxnorm_products AS (
    SELECT
        ('x' || substr(md5(rxcui), 1, 16))::bit(64)::bigint                     AS product_id,
        rxcui,
        NULL::text                                                               AS application_number,
        NULL::text                                                               AS application_product_number,
        NULL::text                                                               AS bla_number,
        NULL::text                                                               AS bla_product_number,
        NULL::text                                                               AS ema_product_number,
        NULL::text                                                               AS cvx_code,
        CASE WHEN tty IN ('SBD', 'BPCK') THEN name ELSE NULL END               AS brand_name,
        CASE WHEN tty IN ('SCD', 'GPCK') THEN name ELSE NULL END               AS generic_name,
        NULL::text                                                               AS dosage_form,
        NULL::text                                                               AS route,
        NULL::numeric                                                            AS strength_normalized_mg,
        FALSE                                                                    AS is_combination,
        FALSE                                                                    AS is_biologic,
        FALSE                                                                    AS is_biosimilar,
        NULL::bigint                                                             AS reference_product_id,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.rxnorm_concepts
    WHERE tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')
      AND rxcui IS NOT NULL
),

all_products AS (
    SELECT *, 1 AS src_priority FROM fda_products
    UNION ALL
    SELECT *, 2 AS src_priority FROM rxnorm_products
),

deduped AS (
    SELECT DISTINCT ON (product_id)
        product_id,
        rxcui,
        bla_number,
        bla_product_number,
        application_number,
        application_product_number,
        ema_product_number,
        cvx_code,
        brand_name,
        generic_name,
        dosage_form,
        route,
        strength_normalized_mg,
        is_combination,
        is_biologic,
        is_biosimilar,
        reference_product_id,
        first_seen_at
    FROM all_products
    ORDER BY product_id, src_priority ASC
)

SELECT
    product_id,
    rxcui,
    bla_number,
    bla_product_number,
    application_number,
    application_product_number,
    ema_product_number,
    cvx_code,
    brand_name,
    generic_name,
    dosage_form,
    route,
    strength_normalized_mg,
    COALESCE(is_combination, FALSE)  AS is_combination,
    COALESCE(is_biologic, FALSE)     AS is_biologic,
    COALESCE(is_biosimilar, FALSE)   AS is_biosimilar,
    reference_product_id,
    COALESCE(first_seen_at, NOW())   AS first_seen_at,
    NOW()                            AS last_updated_at
FROM deduped;

-- CREATE INDEX IF NOT EXISTS mol_silver_dp_brand_idx ON mol_silver.drug_products (brand_name);
-- CREATE INDEX IF NOT EXISTS mol_silver_dp_generic_idx ON mol_silver.drug_products (generic_name);
-- CREATE INDEX IF NOT EXISTS mol_silver_dp_ref_idx ON mol_silver.drug_products (reference_product_id) WHERE reference_product_id IS NOT NULL;

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

purple_book_products AS (
    -- Biologics (BLA) products. is_biosimilar is set from source; reference_product_id
    -- is resolved in a later CTE by looking up brand_name/generic_name from other products.
    SELECT
        ('x' || substr(md5('bla:' || bla_number || ':' || COALESCE(product_number, '0')), 1, 16))::bit(64)::bigint AS product_id,
        NULL::text                                                               AS rxcui,
        NULL::text                                                               AS application_number,
        NULL::text                                                               AS application_product_number,
        NULLIF(bla_number, '')                                                   AS bla_number,
        NULLIF(product_number, '')                                               AS bla_product_number,
        NULL::text                                                               AS ema_product_number,
        NULL::text                                                               AS cvx_code,
        NULLIF(brand_name, '')                                                   AS brand_name,
        NULLIF(generic_name, '')                                                 AS generic_name,
        NULLIF(dosage_form, '')                                                  AS dosage_form,
        NULLIF(route, '')                                                        AS route,
        NULL::numeric                                                            AS strength_normalized_mg,
        FALSE                                                                    AS is_combination,
        TRUE                                                                     AS is_biologic,
        COALESCE(is_biosimilar, FALSE)                                           AS is_biosimilar,
        NULL::bigint                                                             AS reference_product_id,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.purple_book
    WHERE bla_number IS NOT NULL
),

all_products AS (
    SELECT *, 1 AS src_priority FROM fda_products
    UNION ALL
    SELECT *, 2 AS src_priority FROM rxnorm_products
    UNION ALL
    SELECT *, 3 AS src_priority FROM purple_book_products
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
),

-- FR-012a: biosimilar→reference product linkage. Purple Book provides
-- reference_product_name (the originator brand) for each biosimilar. We resolve
-- it to a hub product_id by exact-match on the reference brand_name. Equality-only,
-- no LIKE/similarity (S2/S5 antipatterns banned).
reference_lookup AS (
    SELECT DISTINCT ON (LOWER(brand_name))
        LOWER(brand_name) AS norm_brand,
        product_id        AS reference_product_id
    FROM deduped
    WHERE brand_name IS NOT NULL
      AND is_biologic = TRUE
      AND COALESCE(is_biosimilar, FALSE) = FALSE
    ORDER BY LOWER(brand_name), product_id
),

biosimilar_resolution AS (
    -- Two equi-joins (not OR-join) to keep the planner on hash join. Brand match
    -- takes precedence over generic name match.
    SELECT
        ('x' || substr(md5('bla:' || pb.bla_number || ':' || COALESCE(pb.product_number, '0')), 1, 16))::bit(64)::bigint AS product_id,
        COALESCE(rl_brand.reference_product_id, rl_name.reference_product_id) AS reference_product_id
    FROM mol_bronze.purple_book pb
    LEFT JOIN reference_lookup rl_brand
      ON rl_brand.norm_brand = LOWER(NULLIF(pb.reference_product_brand, ''))
    LEFT JOIN reference_lookup rl_name
      ON rl_name.norm_brand = LOWER(NULLIF(pb.reference_product_name, ''))
    WHERE pb.bla_number IS NOT NULL
      AND COALESCE(pb.is_biosimilar, FALSE) = TRUE
)

SELECT
    d.product_id,
    d.rxcui,
    d.bla_number,
    d.bla_product_number,
    d.application_number,
    d.application_product_number,
    d.ema_product_number,
    d.cvx_code,
    d.brand_name,
    d.generic_name,
    d.dosage_form,
    d.route,
    d.strength_normalized_mg,
    COALESCE(d.is_combination, FALSE)  AS is_combination,
    COALESCE(d.is_biologic, FALSE)     AS is_biologic,
    COALESCE(d.is_biosimilar, FALSE)   AS is_biosimilar,
    COALESCE(br.reference_product_id, d.reference_product_id) AS reference_product_id,
    COALESCE(d.first_seen_at, NOW())   AS first_seen_at,
    NOW()                              AS last_updated_at
FROM deduped d
LEFT JOIN biosimilar_resolution br USING (product_id);

-- CREATE INDEX IF NOT EXISTS mol_silver_dp_brand_idx ON mol_silver.drug_products (brand_name);
-- CREATE INDEX IF NOT EXISTS mol_silver_dp_generic_idx ON mol_silver.drug_products (generic_name);
-- CREATE INDEX IF NOT EXISTS mol_silver_dp_ref_idx ON mol_silver.drug_products (reference_product_id) WHERE reference_product_id IS NOT NULL;

-- T034: mol_silver.drug_product_names — drug product name index
-- Brand names, generic names, and synonyms from FDA and RxNorm.

MODEL (
    name mol_silver.drug_product_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, product_id, source)
    ),
    grain (normalized_name, product_id, source),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH fda_brand_names AS (
    SELECT
        LOWER(TRIM(proprietary_name))                                            AS normalized_name,
        ('x' || substr(md5(COALESCE(rxcui, 'fda:' || LOWER(COALESCE(nonproprietary_name, proprietary_name, application_number || ':' || product_number)))), 1, 16))::bit(64)::bigint AS product_id,
        'brand'                                                                  AS name_kind,
        'fda'                                                                    AS source,
        1.0                                                                      AS confidence,
        proprietary_name                                                         AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.fda_drugs
    WHERE proprietary_name IS NOT NULL

    UNION ALL

    SELECT
        LOWER(TRIM(nonproprietary_name))                                         AS normalized_name,
        ('x' || substr(md5(COALESCE(rxcui, 'fda:' || LOWER(COALESCE(nonproprietary_name, proprietary_name, application_number || ':' || product_number)))), 1, 16))::bit(64)::bigint AS product_id,
        'generic'                                                                AS name_kind,
        'fda'                                                                    AS source,
        1.0                                                                      AS confidence,
        nonproprietary_name                                                      AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.fda_drugs
    WHERE nonproprietary_name IS NOT NULL
),

rxnorm_names AS (
    SELECT
        LOWER(TRIM(name))                                                        AS normalized_name,
        ('x' || substr(md5(rxcui), 1, 16))::bit(64)::bigint                    AS product_id,
        CASE WHEN tty IN ('SBD', 'BPCK') THEN 'brand' ELSE 'generic' END       AS name_kind,
        'rxnorm'                                                                 AS source,
        0.9                                                                      AS confidence,
        name                                                                     AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.rxnorm_concepts
    WHERE tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')
      AND name IS NOT NULL
),

all_names AS (
    SELECT * FROM fda_brand_names
    UNION ALL
    SELECT * FROM rxnorm_names
)

SELECT DISTINCT ON (normalized_name, product_id, source)
    normalized_name,
    product_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND product_id IS NOT NULL
ORDER BY normalized_name, product_id, source, first_seen_at ASC;

-- CREATE INDEX IF NOT EXISTS mol_silver_dp_names_prod_idx ON mol_silver.drug_product_names (product_id);
-- CREATE INDEX IF NOT EXISTS mol_silver_dp_names_gin_idx ON mol_silver.drug_product_names USING GIN (normalized_name gin_trgm_ops);

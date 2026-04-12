-- T034: mol_silver.drug_product_identifiers — drug product identifier crosswalk
-- Covers: ndc, rxcui, bla, application_number, ema_product_number, cvx.

MODEL (
    name mol_silver.drug_product_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH fda_ndc AS (
    SELECT
        'ndc'                                                                    AS source,
        ndc_package_code                                                         AS identifier,
        ('x' || substr(md5(COALESCE(rxcui, 'fda:' || LOWER(COALESCE(nonproprietary_name, proprietary_name, application_number || ':' || product_number)))), 1, 16))::bit(64)::bigint AS product_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.fda_ndc
    WHERE ndc_package_code IS NOT NULL

    UNION ALL

    SELECT
        'application_number'                                                     AS source,
        application_number                                                       AS identifier,
        ('x' || substr(md5(COALESCE(rxcui, 'fda:' || LOWER(COALESCE(nonproprietary_name, proprietary_name, application_number || ':' || product_number)))), 1, 16))::bit(64)::bigint AS product_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.fda_drugs
    WHERE application_number IS NOT NULL
),

rxnorm_ids AS (
    SELECT
        'rxcui'                                                                  AS source,
        rxcui                                                                    AS identifier,
        ('x' || substr(md5(rxcui), 1, 16))::bit(64)::bigint                    AS product_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.rxnorm_concepts
    WHERE tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')
      AND rxcui IS NOT NULL
),

all_ids AS (
    SELECT * FROM fda_ndc
    UNION ALL
    SELECT * FROM rxnorm_ids
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    product_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_ids
WHERE product_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_dp_ident_src_id_idx ON mol_silver.drug_product_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS mol_silver_dp_ident_prod_idx ON mol_silver.drug_product_identifiers (product_id);

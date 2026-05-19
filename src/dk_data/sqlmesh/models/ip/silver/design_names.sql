-- T042: ip_silver.design_names — design product indication / name index

MODEL (
    name ip_silver.design_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, design_id, source)
    ),
    grain (normalized_name, design_id, source)
);

WITH euipo_indications AS (
    SELECT
        LOWER(TRIM(product_indication))                                          AS normalized_name,
        ('x' || substr(md5('EU:' || COALESCE(design_number, application_number)), 1, 16))::bit(64)::bigint AS design_id,
        'product_indication'                                                     AS name_kind,
        'euipo'                                                                  AS source,
        1.0                                                                      AS confidence,
        product_indication                                                       AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.euipo_designs
    WHERE product_indication IS NOT NULL
      AND COALESCE(design_number, application_number) IS NOT NULL
)

SELECT DISTINCT ON (normalized_name, design_id, source)
    normalized_name,
    design_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM euipo_indications
WHERE normalized_name IS NOT NULL
  AND design_id IS NOT NULL
ORDER BY normalized_name, design_id, source, first_seen_at ASC;

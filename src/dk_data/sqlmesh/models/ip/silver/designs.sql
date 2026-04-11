-- T042: ip_silver.designs — industrial design hub (NEW)
-- Hub architecture: one row per unique design keyed by (jurisdiction, design_number).
-- Sources: EUIPO designs from bronze (migrated from mol_bronze.euipo_designs).

MODEL (
    name ip_silver.designs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key design_id
    ),
    grain design_id
);

WITH euipo_designs AS (
    SELECT
        ('x' || substr(md5('EU:' || COALESCE(design_number, application_number)), 1, 16))::bit(64)::bigint AS design_id,
        'EU'                                                                     AS jurisdiction,
        NULLIF(design_number, '')                                                AS design_number,
        NULLIF(wipo_hague_number, '')                                            AS wipo_hague_number,
        locarno_classes,
        filing_date::date                                                        AS filing_date,
        registration_date::date                                                  AS registration_date,
        NULL::bigint                                                             AS holder_company_id,
        NULLIF(product_indication, '')                                           AS product_indication,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.euipo_designs
    WHERE COALESCE(design_number, application_number) IS NOT NULL
),

deduped AS (
    SELECT DISTINCT ON (design_id)
        design_id,
        jurisdiction,
        design_number,
        wipo_hague_number,
        locarno_classes,
        filing_date,
        registration_date,
        holder_company_id,
        product_indication,
        first_seen_at
    FROM euipo_designs
    ORDER BY design_id, src_priority ASC
)

SELECT
    design_id,
    jurisdiction,
    design_number,
    wipo_hague_number,
    locarno_classes,
    filing_date,
    registration_date,
    holder_company_id,
    product_indication,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- CREATE INDEX IF NOT EXISTS ip_silver_des_holder_idx ON ip_silver.designs (holder_company_id);
-- CREATE INDEX IF NOT EXISTS ip_silver_des_gin_classes_idx ON ip_silver.designs USING GIN (locarno_classes);

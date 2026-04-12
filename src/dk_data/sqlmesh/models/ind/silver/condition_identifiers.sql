-- T036: ind_silver.condition_identifiers — condition identifier crosswalk
-- Covers: icd11, icd10, mesh, meddra_pt, snomed, omim.

MODEL (
    name ind_silver.condition_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier)
);

WITH icd_ids AS (
    SELECT
        'icd10'                                                                  AS source,
        icd10_code                                                               AS identifier,
        ('x' || substr(md5(COALESCE(icd11_code, icd10_code, mesh_id, meddra_pt, LOWER(condition_name))), 1, 16))::bit(64)::bigint AS condition_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd_codes
    WHERE icd10_code IS NOT NULL

    UNION ALL

    SELECT
        'icd11'                                                                  AS source,
        icd11_code                                                               AS identifier,
        ('x' || substr(md5(COALESCE(icd11_code, icd10_code, mesh_id, meddra_pt, LOWER(condition_name))), 1, 16))::bit(64)::bigint AS condition_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd_codes
    WHERE icd11_code IS NOT NULL

    UNION ALL

    SELECT
        'mesh'                                                                   AS source,
        mesh_id                                                                  AS identifier,
        ('x' || substr(md5(COALESCE(icd11_code, icd10_code, mesh_id, meddra_pt, LOWER(condition_name))), 1, 16))::bit(64)::bigint AS condition_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd_codes
    WHERE mesh_id IS NOT NULL

    UNION ALL

    SELECT
        'meddra_pt'                                                              AS source,
        meddra_pt                                                                AS identifier,
        ('x' || substr(md5(COALESCE(icd11_code, icd10_code, mesh_id, meddra_pt, LOWER(condition_name))), 1, 16))::bit(64)::bigint AS condition_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd_codes
    WHERE meddra_pt IS NOT NULL
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    condition_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM icd_ids
WHERE condition_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS ind_silver_cond_ident_src_id_idx ON ind_silver.condition_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS ind_silver_cond_ident_cond_idx ON ind_silver.condition_identifiers (condition_id);

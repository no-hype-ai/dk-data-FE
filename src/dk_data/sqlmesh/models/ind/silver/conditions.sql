-- T036: ind_silver.conditions — disease / condition hub
-- Hub architecture: one row per unique condition keyed by ICD-11 > ICD-10 > MeSH > MedDRA PT.
-- Unique constraints: icd11_code, icd10_code, mesh_descriptor_id, meddra_pt (each separately).

MODEL (
    name ind_silver.conditions,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key condition_id
    ),
    grain condition_id
);

WITH icd_conditions AS (
    SELECT
        ('x' || substr(md5(COALESCE(icd11_code, icd10_code, mesh_id, meddra_pt, LOWER(condition_name))), 1, 16))::bit(64)::bigint AS condition_id,
        NULLIF(icd11_code, '')                                                   AS icd11_code,
        NULLIF(icd10_code, '')                                                   AS icd10_code,
        NULLIF(mesh_id, '')                                                      AS mesh_descriptor_id,
        NULLIF(meddra_pt, '')                                                    AS meddra_pt,
        COALESCE(condition_name, label, icd10_code)                              AS canonical_name,
        therapeutic_area,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd_codes
    WHERE COALESCE(icd11_code, icd10_code, mesh_id, meddra_pt, condition_name) IS NOT NULL
),

icd11_conditions AS (
    SELECT
        ('x' || substr(md5(code), 1, 16))::bit(64)::bigint                     AS condition_id,
        code                                                                     AS icd11_code,
        NULL::text                                                               AS icd10_code,
        NULL::text                                                               AS mesh_descriptor_id,
        NULL::text                                                               AS meddra_pt,
        COALESCE(title, code)                                                    AS canonical_name,
        NULL::text                                                               AS therapeutic_area,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM ind_bronze.icd11_codes
    WHERE code IS NOT NULL
),

all_conditions AS (
    SELECT * FROM icd_conditions
    UNION ALL
    SELECT * FROM icd11_conditions
),

deduped AS (
    SELECT DISTINCT ON (condition_id)
        condition_id,
        icd11_code,
        icd10_code,
        mesh_descriptor_id,
        meddra_pt,
        canonical_name,
        therapeutic_area,
        first_seen_at
    FROM all_conditions
    ORDER BY condition_id, src_priority ASC
)

SELECT
    condition_id,
    icd11_code,
    icd10_code,
    mesh_descriptor_id,
    meddra_pt,
    canonical_name,
    therapeutic_area,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- Unique constraints + trigram index applied via migration 031_silver_hub_rebuild/001_hub_indexes.sql.
-- CREATE INDEX IF NOT EXISTS ind_silver_cond_canonical_idx ON ind_silver.conditions (canonical_name);
-- CREATE INDEX IF NOT EXISTS ind_silver_cond_gin_idx ON ind_silver.conditions USING GIN (LOWER(canonical_name) gin_trgm_ops);

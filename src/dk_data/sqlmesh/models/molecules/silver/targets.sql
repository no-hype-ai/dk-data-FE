-- T035: mol_silver.targets — biological target hub
-- Hub architecture: one row per unique target (protein/enzyme/receptor/etc.).
-- Identity: UniProt ID (primary) or ChEMBL target ID or gene symbol.

MODEL (
    name mol_silver.targets,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key target_id
    ),
    grain target_id
);

WITH chembl_targets AS (
    SELECT
        ('x' || substr(md5(COALESCE(uniprot_id, chembl_target_id)), 1, 16))::bit(64)::bigint AS target_id,
        NULLIF(uniprot_id, '')                                                   AS uniprot_id,
        NULL::text                                                               AS sequence_hash,
        COALESCE(pref_name, target_name, chembl_target_id)                      AS canonical_name,
        target_type,
        organism,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.protein_targets
    WHERE COALESCE(uniprot_id, chembl_target_id) IS NOT NULL
),

uniprot_targets AS (
    SELECT
        ('x' || substr(md5(accession), 1, 16))::bit(64)::bigint                 AS target_id,
        accession                                                                AS uniprot_id,
        sequence_hash,
        COALESCE(protein_name, accession)                                        AS canonical_name,
        'protein'                                                                AS target_type,
        organism,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.uniprot
    WHERE accession IS NOT NULL
),

all_targets AS (
    SELECT * FROM chembl_targets
    UNION ALL
    SELECT * FROM uniprot_targets
),

deduped AS (
    SELECT DISTINCT ON (target_id)
        target_id,
        uniprot_id,
        sequence_hash,
        canonical_name,
        target_type,
        organism,
        first_seen_at
    FROM all_targets
    ORDER BY target_id, src_priority ASC
)

SELECT
    target_id,
    uniprot_id,
    sequence_hash,
    canonical_name,
    target_type,
    organism,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- CREATE INDEX IF NOT EXISTS mol_silver_tgt_canonical_idx ON mol_silver.targets (canonical_name);
-- CREATE INDEX IF NOT EXISTS mol_silver_tgt_gin_idx ON mol_silver.targets USING GIN (LOWER(canonical_name) gin_trgm_ops);
-- CREATE INDEX IF NOT EXISTS mol_silver_tgt_seq_hash_idx ON mol_silver.targets (sequence_hash) WHERE sequence_hash IS NOT NULL;

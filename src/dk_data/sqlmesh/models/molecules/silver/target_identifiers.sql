-- T035: mol_silver.target_identifiers — target identifier crosswalk
-- Covers: uniprot, chembl_target, gene_symbol, entrez, ensembl, pdb.

MODEL (
    name mol_silver.target_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier)
);

WITH chembl_ids AS (
    SELECT
        'chembl_target'                                                          AS source,
        chembl_target_id                                                         AS identifier,
        ('x' || substr(md5(COALESCE(uniprot_id, chembl_target_id)), 1, 16))::bit(64)::bigint AS target_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.protein_targets
    WHERE chembl_target_id IS NOT NULL

    UNION ALL

    SELECT
        'uniprot'                                                                AS source,
        uniprot_id                                                               AS identifier,
        ('x' || substr(md5(COALESCE(uniprot_id, chembl_target_id)), 1, 16))::bit(64)::bigint AS target_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.protein_targets
    WHERE uniprot_id IS NOT NULL

    UNION ALL

    SELECT
        'gene_symbol'                                                            AS source,
        gene_symbol                                                              AS identifier,
        ('x' || substr(md5(COALESCE(uniprot_id, chembl_target_id)), 1, 16))::bit(64)::bigint AS target_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.protein_targets
    WHERE gene_symbol IS NOT NULL
),

uniprot_ids AS (
    SELECT
        'uniprot'                                                                AS source,
        accession                                                                AS identifier,
        ('x' || substr(md5(accession), 1, 16))::bit(64)::bigint                AS target_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.uniprot
    WHERE accession IS NOT NULL
),

all_ids AS (
    SELECT * FROM chembl_ids
    UNION ALL
    SELECT * FROM uniprot_ids
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    target_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_ids
WHERE target_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_tgt_ident_src_id_idx ON mol_silver.target_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS mol_silver_tgt_ident_tgt_idx ON mol_silver.target_identifiers (target_id);

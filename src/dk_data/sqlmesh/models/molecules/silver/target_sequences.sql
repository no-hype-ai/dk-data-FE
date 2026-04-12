-- T035: mol_silver.target_sequences — target sequence records
-- One row per (target_id, sequence_db, accession). PK is compound.

MODEL (
    name mol_silver.target_sequences,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (target_id, sequence_db, accession)
    ),
    grain (target_id, sequence_db, accession),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH uniprot_seqs AS (
    SELECT
        ('x' || substr(md5(u.accession), 1, 16))::bit(64)::bigint               AS target_id,
        'uniprot'                                                                AS sequence_db,
        u.accession                                                              AS accession,
        u.sequence                                                               AS sequence,
        u.ingested_at                                                            AS first_seen_at
    FROM mol_bronze.uniprot u
    WHERE u.accession IS NOT NULL
      AND u.sequence IS NOT NULL
),

imgt_seqs AS (
    SELECT
        ('x' || substr(md5(COALESCE(pt.uniprot_id, pt.chembl_target_id)), 1, 16))::bit(64)::bigint AS target_id,
        'imgt'                                                                   AS sequence_db,
        i.accession                                                              AS accession,
        i.sequence                                                               AS sequence,
        i.ingested_at                                                            AS first_seen_at
    FROM mol_bronze.imgt i
    JOIN mol_bronze.protein_targets pt ON LOWER(i.gene_symbol) = LOWER(pt.gene_symbol)
    WHERE i.accession IS NOT NULL
      AND i.sequence IS NOT NULL
),

all_seqs AS (
    SELECT * FROM uniprot_seqs
    UNION ALL
    SELECT * FROM imgt_seqs
)

SELECT DISTINCT ON (target_id, sequence_db, accession)
    target_id,
    sequence_db,
    accession,
    sequence,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_seqs
WHERE target_id IS NOT NULL
ORDER BY target_id, sequence_db, accession, first_seen_at ASC;

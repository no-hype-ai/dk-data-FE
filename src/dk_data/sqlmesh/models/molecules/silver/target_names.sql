-- T035: mol_silver.target_names — target name index
-- Canonical names, gene symbols, and aliases from ChEMBL and UniProt.

MODEL (
    name mol_silver.target_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, target_id, source)
    ),
    grain (normalized_name, target_id, source),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH chembl_names AS (
    SELECT
        LOWER(TRIM(COALESCE(pref_name, target_name, chembl_target_id)))         AS normalized_name,
        ('x' || substr(md5(COALESCE(uniprot_id, chembl_target_id)), 1, 16))::bit(64)::bigint AS target_id,
        'canonical'                                                              AS name_kind,
        'chembl'                                                                 AS source,
        1.0                                                                      AS confidence,
        COALESCE(pref_name, target_name, chembl_target_id)                      AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.protein_targets
    WHERE COALESCE(pref_name, target_name, chembl_target_id) IS NOT NULL

    UNION ALL

    SELECT
        LOWER(TRIM(gene_symbol))                                                 AS normalized_name,
        ('x' || substr(md5(COALESCE(uniprot_id, chembl_target_id)), 1, 16))::bit(64)::bigint AS target_id,
        'gene_symbol'                                                            AS name_kind,
        'chembl'                                                                 AS source,
        0.95                                                                     AS confidence,
        gene_symbol                                                              AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.protein_targets
    WHERE gene_symbol IS NOT NULL
),

uniprot_names AS (
    SELECT
        LOWER(TRIM(protein_name))                                                AS normalized_name,
        ('x' || substr(md5(accession), 1, 16))::bit(64)::bigint                AS target_id,
        'canonical'                                                              AS name_kind,
        'uniprot'                                                                AS source,
        1.0                                                                      AS confidence,
        protein_name                                                             AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.uniprot
    WHERE protein_name IS NOT NULL
),

all_names AS (
    SELECT * FROM chembl_names
    UNION ALL
    SELECT * FROM uniprot_names
)

SELECT DISTINCT ON (normalized_name, target_id, source)
    normalized_name,
    target_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND target_id IS NOT NULL
ORDER BY normalized_name, target_id, source, first_seen_at ASC;

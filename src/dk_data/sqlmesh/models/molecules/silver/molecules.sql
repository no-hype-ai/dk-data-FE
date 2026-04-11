-- T030: mol_silver.molecules — canonical molecule hub
-- Hub architecture: one row per unique chemical entity.
-- Structural identity: InChIKey (small molecules) or 'bio:'+lower(name) (biologics).
-- PK is deterministic bigint from hash of identity_key for idempotent upserts.
-- Indexes: canonical_name (btree), LOWER(canonical_name) gin_trgm_ops (trigram fuzzy).

MODEL (
    name mol_silver.molecules,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key molecule_id
    ),
    grain molecule_id
);

WITH ranked AS (
    -- Source 1: ChEMBL structural (inchi_key IS NOT NULL, highest confidence)
    SELECT
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(COALESCE(pref_name, chembl_id)))), 1, 16))::bit(64)::bigint   AS molecule_id,
        COALESCE(inchi_key, NULL)                                    AS inchi_key,
        canonical_smiles,
        NULL::text                                                    AS sequence_hash,
        (molecule_type NOT IN ('Small molecule', 'SMALL_MOLECULE'))  AS is_biologic,
        NULL::bigint                                                  AS parent_molecule_id,
        COALESCE(pref_name, chembl_id)                               AS canonical_name,
        1                                                             AS src_priority,
        MIN(ingested_at) OVER (PARTITION BY COALESCE(inchi_key, 'bio:' || LOWER(COALESCE(pref_name, chembl_id))))  AS first_seen_at
    FROM mol_bronze.chembl_molecules
    WHERE COALESCE(pref_name, chembl_id) IS NOT NULL

    UNION ALL

    -- Source 2: DrugBank (structural + biologic drugs)
    SELECT
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(name))), 1, 16))::bit(64)::bigint  AS molecule_id,
        inchi_key,
        smiles                                                        AS canonical_smiles,
        NULL::text                                                    AS sequence_hash,
        (drug_type IN ('biotech', 'Biotech'))                        AS is_biologic,
        NULL::bigint                                                  AS parent_molecule_id,
        name                                                          AS canonical_name,
        2                                                             AS src_priority,
        MIN(ingested_at) OVER (PARTITION BY COALESCE(inchi_key, 'bio:' || LOWER(name)))  AS first_seen_at
    FROM mol_bronze.drugbank
    WHERE name IS NOT NULL

    UNION ALL

    -- Source 3: PubChem (structural, IUPAC name)
    SELECT
        ('x' || substr(md5(inchi_key), 1, 16))::bit(64)::bigint      AS molecule_id,
        inchi_key,
        canonical_smiles,
        NULL::text                                                    AS sequence_hash,
        FALSE                                                         AS is_biologic,
        NULL::bigint                                                  AS parent_molecule_id,
        COALESCE(iupac_name, 'pubchem:' || cid::text)                AS canonical_name,
        3                                                             AS src_priority,
        MIN(ingested_at) OVER (PARTITION BY inchi_key)               AS first_seen_at
    FROM mol_bronze.pubchem
    WHERE inchi_key IS NOT NULL
      AND COALESCE(iupac_name, cid::text) IS NOT NULL
),

deduped AS (
    SELECT DISTINCT ON (molecule_id)
        molecule_id,
        inchi_key,
        canonical_smiles,
        sequence_hash,
        is_biologic,
        parent_molecule_id,
        canonical_name,
        first_seen_at
    FROM ranked
    ORDER BY molecule_id, src_priority ASC
)

SELECT
    molecule_id,
    inchi_key,
    canonical_smiles,
    sequence_hash,
    COALESCE(is_biologic, FALSE)   AS is_biologic,
    parent_molecule_id,
    canonical_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- Indexes (applied via migration 031_silver_hub_rebuild/001_hub_indexes.sql):
-- CREATE INDEX IF NOT EXISTS mol_silver_molecules_canonical_name_idx ON mol_silver.molecules (canonical_name);
-- CREATE INDEX IF NOT EXISTS mol_silver_molecules_gin_name_idx ON mol_silver.molecules USING GIN (LOWER(canonical_name) gin_trgm_ops);
-- CREATE INDEX IF NOT EXISTS mol_silver_molecules_parent_idx ON mol_silver.molecules (parent_molecule_id) WHERE parent_molecule_id IS NOT NULL;
-- CREATE INDEX IF NOT EXISTS mol_silver_molecules_seq_hash_idx ON mol_silver.molecules (sequence_hash) WHERE sequence_hash IS NOT NULL;

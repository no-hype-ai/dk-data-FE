-- T031: mol_silver.molecule_identifiers — molecule identifier crosswalk
-- One row per (source, identifier) pair linking external IDs to mol_silver.molecules.
-- Covers: chembl, drugbank, pubchem, rxnorm, unii, cas, inn, ndc, inchi.

MODEL (
    name mol_silver.molecule_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier)
);

WITH chembl_ids AS (
    SELECT
        'chembl'                                                                 AS source,
        chembl_id                                                                AS identifier,
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(COALESCE(pref_name, chembl_id)))), 1, 16))::bit(64)::bigint AS molecule_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.chembl_molecules
    WHERE chembl_id IS NOT NULL

    UNION ALL

    SELECT
        'inchi'                                                                  AS source,
        inchi_key                                                                AS identifier,
        ('x' || substr(md5(inchi_key), 1, 16))::bit(64)::bigint                AS molecule_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.chembl_molecules
    WHERE inchi_key IS NOT NULL
),

drugbank_ids AS (
    SELECT
        'drugbank'                                                               AS source,
        drugbank_id                                                              AS identifier,
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(name))), 1, 16))::bit(64)::bigint AS molecule_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.drugbank
    WHERE drugbank_id IS NOT NULL

    UNION ALL

    SELECT
        'cas'                                                                    AS source,
        cas_number                                                               AS identifier,
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(name))), 1, 16))::bit(64)::bigint AS molecule_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.drugbank
    WHERE cas_number IS NOT NULL

    UNION ALL

    SELECT
        'unii'                                                                   AS source,
        unii                                                                     AS identifier,
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(name))), 1, 16))::bit(64)::bigint AS molecule_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.drugbank
    WHERE unii IS NOT NULL
),

pubchem_ids AS (
    SELECT
        'pubchem'                                                                AS source,
        cid::text                                                                AS identifier,
        ('x' || substr(md5(inchi_key), 1, 16))::bit(64)::bigint                AS molecule_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.pubchem
    WHERE cid IS NOT NULL
      AND inchi_key IS NOT NULL
),

all_ids AS (
    SELECT * FROM chembl_ids
    UNION ALL
    SELECT * FROM drugbank_ids
    UNION ALL
    SELECT * FROM pubchem_ids
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    molecule_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_ids
WHERE molecule_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_mol_ident_src_id_idx ON mol_silver.molecule_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS mol_silver_mol_ident_mol_idx ON mol_silver.molecule_identifiers (molecule_id);

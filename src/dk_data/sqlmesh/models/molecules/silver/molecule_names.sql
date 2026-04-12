-- T032: mol_silver.molecule_names — molecule name index
-- One row per (normalized_name, molecule_id, source) — canonical + all synonym variants.
-- Used by fuzzy name resolution in mol_silver.resolve_molecule().

MODEL (
    name mol_silver.molecule_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, molecule_id, source)
    ),
    grain (normalized_name, molecule_id, source)
    ,
    -- T4: large input — raise work_mem to keep sorts in memory (per-session 256MB ceiling per FR-021b)
);

WITH chembl_names AS (
    SELECT
        LOWER(TRIM(pref_name))                                                   AS normalized_name,
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(COALESCE(pref_name, chembl_id)))), 1, 16))::bit(64)::bigint AS molecule_id,
        'canonical'                                                              AS name_kind,
        'chembl'                                                                 AS source,
        1.0                                                                      AS confidence,
        pref_name                                                                AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.chembl_molecules
    WHERE pref_name IS NOT NULL
),

drugbank_names AS (
    -- Generic/canonical name
    SELECT
        LOWER(TRIM(name))                                                        AS normalized_name,
        ('x' || substr(md5(COALESCE(inchi_key, 'bio:' || LOWER(name))), 1, 16))::bit(64)::bigint AS molecule_id,
        'generic'                                                                AS name_kind,
        'drugbank'                                                               AS source,
        0.9                                                                      AS confidence,
        name                                                                     AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.drugbank
    WHERE name IS NOT NULL
),

pubchem_iupac AS (
    SELECT
        LOWER(TRIM(iupac_name))                                                  AS normalized_name,
        ('x' || substr(md5(inchi_key), 1, 16))::bit(64)::bigint                AS molecule_id,
        'iupac'                                                                  AS name_kind,
        'pubchem'                                                                AS source,
        0.8                                                                      AS confidence,
        iupac_name                                                               AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.pubchem
    WHERE inchi_key IS NOT NULL
      AND iupac_name IS NOT NULL
),

all_names AS (
    SELECT * FROM chembl_names
    UNION ALL
    SELECT * FROM drugbank_names
    UNION ALL
    SELECT * FROM pubchem_iupac
)

SELECT DISTINCT ON (normalized_name, molecule_id, source)
    normalized_name,
    molecule_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND molecule_id IS NOT NULL
ORDER BY normalized_name, molecule_id, source, first_seen_at ASC;

-- CREATE INDEX IF NOT EXISTS mol_silver_mol_names_mol_idx ON mol_silver.molecule_names (molecule_id);
-- CREATE INDEX IF NOT EXISTS mol_silver_mol_names_gin_idx ON mol_silver.molecule_names USING GIN (normalized_name gin_trgm_ops);

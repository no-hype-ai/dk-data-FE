-- T034: mol_silver.drug_product_ingredients — drug product to molecule bridge
-- Links drug products to their active/inactive ingredient molecules.
-- Compound PK: (product_id, molecule_id).

MODEL (
    name mol_silver.drug_product_ingredients,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (product_id, molecule_id)
    ),
    grain (product_id, molecule_id)
    ,
    -- T4: large input — raise work_mem to keep sorts in memory (per-session 256MB ceiling per FR-021b)
);

WITH rxnorm_ingredients AS (
    -- RxNorm ingredient relationships via SCDF/SBDF
    SELECT
        ('x' || substr(md5(rxcui_product), 1, 16))::bit(64)::bigint             AS product_id,
        ('x' || substr(md5(COALESCE(inchi_key_ing, 'bio:' || LOWER(COALESCE(pref_name_ing, chembl_id_ing)))), 1, 16))::bit(64)::bigint AS molecule_id,
        NULL::numeric                                                            AS strength_value,
        NULL::text                                                               AS strength_unit,
        TRUE                                                                     AS is_active,
        1                                                                        AS ingredient_order
    FROM (
        SELECT
            r.rxcui AS rxcui_product,
            c.inchi_key AS inchi_key_ing,
            c.pref_name AS pref_name_ing,
            c.chembl_id AS chembl_id_ing
        FROM mol_bronze.rxnorm_concepts r
        JOIN mol_bronze.chembl_molecules c
          ON LOWER(r.ingredient_name) = LOWER(c.pref_name)
        WHERE r.tty IN ('SCD', 'SBD', 'GPCK', 'BPCK')
          AND r.ingredient_name IS NOT NULL
    ) ingredient_join
    WHERE product_id IS NOT NULL
      AND molecule_id IS NOT NULL
)

SELECT DISTINCT ON (product_id, molecule_id)
    product_id,
    molecule_id,
    strength_value,
    strength_unit,
    COALESCE(is_active, TRUE)       AS is_active,
    ingredient_order
FROM rxnorm_ingredients
ORDER BY product_id, molecule_id;

-- CREATE INDEX IF NOT EXISTS mol_silver_dpi_mol_idx ON mol_silver.drug_product_ingredients (molecule_id);

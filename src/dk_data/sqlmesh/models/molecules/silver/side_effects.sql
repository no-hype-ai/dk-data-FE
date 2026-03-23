-- SQLMesh Model: Silver Side Effects
-- Promotes mol_bronze.sider into mol_silver.side_effects with molecule_id linkage.
-- Entity linking: stitch_id (STITCH/PubChem CID) → mol_silver.pubchem.pubchem_cid → molecule_id.
-- Fallback: drug_name → mol_silver.molecules.canonical_name.

MODEL (
    name mol_silver.side_effects,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (stitch_id, side_effect_name))
    )
);

SELECT
    gen_random_uuid()                                       AS id,
    COALESCE(p.molecule_id, m_name.molecule_id)            AS molecule_id,
    b.stitch_id,
    b.pubchem_cid,
    b.drug_name,
    b.meddra_concept_id,
    b.side_effect_name,
    b.meddra_level,
    b.frequency_raw,
    b.frequency_lower,
    b.frequency_upper,
    b.frequency_description,
    b.frequency_category,
    b.placebo_frequency,
    b.indication,
    b.indication_source,
    'sider'                                                AS source,
    b.ingested_at                                          AS created_at

FROM mol_bronze.sider b
-- Link via PubChem CID → pubchem silver → molecule
LEFT JOIN mol_silver.pubchem pc
       ON b.pubchem_cid IS NOT NULL
      AND b.pubchem_cid = pc.pubchem_cid::TEXT
LEFT JOIN mol_silver.molecules p
       ON pc.molecule_id IS NOT NULL
      AND p.molecule_id = pc.molecule_id
-- Fallback: drug_name → canonical_name
LEFT JOIN mol_silver.molecules m_name
       ON p.molecule_id IS NULL
      AND b.drug_name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.drug_name)
WHERE b.stitch_id IS NOT NULL
  AND b.side_effect_name IS NOT NULL;

-- SQLMesh Model: Silver Side Effects
-- Promotes mol_bronze.sider into mol_silver.side_effects with molecule_id linkage.
-- Entity linking: stitch_id_flat (STITCH/PubChem CID) → mol_silver.pubchem → molecule_id.
--
-- SIDER does not carry drug names; all linkage is via PubChem CID derived from
-- the STITCH flat ID (CIDmNNNNNNNN → strip prefix → numeric CID).
--
-- Note: mol_silver.adverse_events (in the silver schema) aggregates FAERS + SIDER
-- at the molecule+MedDRA_PT level. This model preserves row-level SIDER data
-- with full frequency detail for use in mol_gold drug profiles.

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
    pc.molecule_id                                          AS molecule_id,
    b.stitch_id_flat                                        AS stitch_id,
    b.pubchem_cid,
    -- drug_name from mol_silver.molecules via molecule_id JOIN (SIDER has no name field)
    m.canonical_name                                        AS drug_name,
    b.umls_cui_side_effect                                  AS meddra_concept_id,
    b.side_effect_name,
    b.meddra_concept_type                                   AS meddra_level,
    b.frequency_raw,
    b.lower_bound_freq                                      AS frequency_lower,
    b.upper_bound_freq                                      AS frequency_upper,
    -- SIDER has no free-text frequency description field
    NULL::TEXT                                              AS frequency_description,
    b.frequency_category,
    b.placebo                                               AS placebo_frequency,
    -- SIDER contains side effects, not indications
    NULL::TEXT                                              AS indication,
    NULL::TEXT                                              AS indication_source,
    'sider'                                                 AS source,
    b.ingested_at                                           AS created_at

FROM mol_bronze.sider b
-- Link via PubChem CID → mol_silver.pubchem → molecule_id
LEFT JOIN mol_silver.pubchem pc
       ON b.pubchem_cid IS NOT NULL
      AND b.pubchem_cid = pc.cid
-- Get canonical_name as drug_name from molecules
LEFT JOIN mol_silver.molecules m ON pc.molecule_id IS NOT NULL
    AND pc.molecule_id = m.molecule_id

WHERE b.stitch_id_flat IS NOT NULL
  AND b.side_effect_name IS NOT NULL;

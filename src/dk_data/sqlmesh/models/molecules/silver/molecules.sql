-- SQLMesh External Model: Silver Molecules
-- mol_silver.molecules is managed by Xenon onboarding, not SQLMesh.
-- kind EXTERNAL tells SQLMesh this table is managed externally — the SELECT
-- defines the schema for lineage tracking only and is never executed.
-- The physical prod table is populated by the Xenon onboarding API.

MODEL (
    name mol_silver.molecules,
    kind EXTERNAL
);

-- Schema definition for lineage (never executed, values don't matter)
SELECT
    NULL::UUID        AS molecule_id,
    NULL::TEXT        AS inchi_key,
    NULL::TEXT        AS chembl_id,
    NULL::TEXT        AS drugbank_id,
    NULL::TEXT        AS pubchem_cid,
    NULL::TEXT        AS rxnorm_cui,
    NULL::TEXT        AS unii,
    NULL::TEXT        AS cas_number,
    NULL::TEXT        AS canonical_name,
    NULL::TEXT        AS canonical_smiles,
    NULL::TEXT        AS inchi,
    NULL::TEXT        AS molecular_formula,
    NULL::NUMERIC     AS molecular_weight,
    NULL::TEXT        AS molecule_type,
    NULL::BOOLEAN     AS needs_review,
    NULL::TEXT        AS review_reason,
    NULL::NUMERIC     AS resolution_confidence,
    NULL::TIMESTAMPTZ AS reviewed_at,
    NULL::TEXT        AS reviewed_by,
    NULL::TIMESTAMPTZ AS created_at,
    NULL::TIMESTAMPTZ AS updated_at,
    NULL::INT         AS source_count,
    NULL::TEXT        AS mechanism_of_action,
    NULL::INT         AS max_phase

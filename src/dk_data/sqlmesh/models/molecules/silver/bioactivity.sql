-- SQLMesh Model: Silver Bioactivity
-- Normalized bioactivity data from ChEMBL activity assay measurements.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Source: mol_bronze.chembl_activities (ChEMBL /api/data/activity endpoint)
-- Entity linking:
--   molecule_id: chembl_id → mol_silver.molecule_identifiers (source='chembl')
--   target_id:  target_chembl_id → mol_silver.target_identifiers (source='chembl')
--              fallback: target_pref_name → mol_silver.target_names (normalized_name)
--
-- T118 verified: rewrite uses hub equi-join, zero S1-S5 antipatterns per test_silver_antipatterns.py

MODEL (
    name mol_silver.bioactivity,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key activity_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (activity_id, chembl_id))
    ),
    grain activity_id
);

-- Staleness guard (FR-050): abort if ChEMBL activities bronze is stale
WITH staleness_check AS (
  SELECT CASE
    WHEN MAX(source_updated_at) < NOW() - INTERVAL '6 hours'
    THEN error('Bronze upstream is stale: mol_bronze.chembl_activities last updated ' || MAX(source_updated_at)::text)
  END FROM mol_bronze.chembl_activities
)

SELECT
    gen_random_uuid()                                               AS id,
    b.chembl_id,

    -- molecule_id: hub equi-join via mol_silver.molecule_identifiers (source='chembl')
    -- Replaces correlated scalar subquery (S3 antipattern) from prior version.
    mi.molecule_id                                                  AS molecule_id,

    -- target_id: hub equi-join via mol_silver.target_identifiers (source='chembl')
    -- Fallback: mol_silver.target_names on normalized target preferred name.
    -- Replaces two correlated scalar subqueries (S3 antipattern) from prior version.
    COALESCE(ti.target_id, tn.target_id)                           AS target_id,

    b.activity_id,
    b.assay_chembl_id,
    b.assay_type,
    b.assay_description,
    b.target_chembl_id,
    b.target_pref_name,
    b.target_type,
    b.target_organism,

    -- Activity measurements
    b.activity_type,
    b.activity_value,
    b.activity_unit,
    b.standard_relation,
    b.pchembl_value,

    -- Activity flags
    b.activity_comment,
    b.data_validity_comment,
    b.potential_duplicate,

    -- Ligand structure
    b.canonical_smiles,

    -- Document reference
    b.document_chembl_id,
    NULL::BIGINT                                                    AS pubmed_id,
    b.publication_year,

    b.source,
    b.source_updated_at,
    b.ingested_at,
    NOW()                                                           AS created_at

FROM staleness_check, mol_bronze.chembl_activities b
-- Tier 1: ChEMBL molecule ID via hub crosswalk
LEFT JOIN mol_silver.molecule_identifiers mi
    ON mi.source = 'chembl'
    AND mi.identifier = b.chembl_id
-- Tier 1: ChEMBL target ID via hub crosswalk
LEFT JOIN mol_silver.target_identifiers ti
    ON ti.source = 'chembl'
    AND ti.identifier = b.target_chembl_id
-- Tier 2 target fallback: normalized preferred name
LEFT JOIN mol_silver.target_names tn
    ON ti.target_id IS NULL
    AND tn.normalized_name = LOWER(b.target_pref_name)
WHERE b.activity_id IS NOT NULL
  AND b.chembl_id IS NOT NULL;

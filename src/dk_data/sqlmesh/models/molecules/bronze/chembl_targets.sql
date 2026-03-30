-- SQLMesh Model: Bronze ChEMBL Targets
-- Distinct target records derived from ChEMBL activity assay data.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Source: mol_bronze.chembl_activities (already ingested)
-- Each activity record carries full target metadata; this model de-duplicates
-- them into one row per ChEMBL target ID.
--
-- Note: This table is used by mol_silver.targets to populate chembl_target_id
-- via name-based enrichment, and by mol_silver.bioactivity as a fallback
-- target resolution path.

MODEL (
    name mol_bronze.chembl_targets,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (chembl_target_id)),
        unique_values(columns := (chembl_target_id))
    ),
    grain chembl_target_id
);

SELECT
    target_chembl_id                                AS chembl_target_id,
    MAX(target_pref_name)                           AS target_pref_name,
    MAX(target_type)                                AS target_type,
    MAX(target_organism)                            AS target_organism,
    'chembl_activities'                             AS source,
    MAX(source_updated_at)                          AS source_updated_at,
    NOW()                                           AS created_at

FROM mol_bronze.chembl_activities
WHERE target_chembl_id IS NOT NULL
GROUP BY target_chembl_id;

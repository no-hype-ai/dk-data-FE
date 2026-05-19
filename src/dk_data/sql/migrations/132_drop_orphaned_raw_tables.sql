-- Migration 132: Drop orphaned raw tables with no loader or superseded by renames
--
-- mol_raw.fda_drugsfda    — never written to; FDADrugsFetcher writes to mol_raw.fda_drugs.
--                           mol_bronze.fda_drugsfda was merged into mol_bronze.fda_drugs.
-- mol_raw.ct_gov_indication_stats — never written to; derived stats computed from
--                           mol_raw.clinicaltrials → mol_bronze.ct_gov_indication_stats.
-- raw.pdb_structures      — orphaned; mol_raw.pdb is the canonical PDB table (migration 127).
-- raw.pipeline_jobs       — superseded by meta.pipeline_jobs (migration 103).
--
-- raw.trademark_status_history is NOT dropped here — it is actively written to by the
-- USPTO and EUIPO loaders and feeds mol_bronze.trademark_status_history (migration 133).
-- raw.websearch is NOT dropped — migration 095 renamed it to mol_raw.websearch in-place.
--
-- Ref: issue #171 M5

DROP TABLE IF EXISTS mol_raw.fda_drugsfda         CASCADE;
DROP TABLE IF EXISTS mol_raw.ct_gov_indication_stats CASCADE;
DROP TABLE IF EXISTS raw.pdb_structures            CASCADE;
DROP TABLE IF EXISTS raw.pipeline_jobs             CASCADE;

-- ROLLBACK: Migration 114 — CMS PUF & Platform Data Reconciliation
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
--
-- ⚠️  WARNING: This rollback is DESTRUCTIVE AND IRREVERSIBLE.
-- It permanently deletes all data ingested by this feature.
-- The following will be lost:
--   - All hcs_raw, hcs_bronze, hcs_silver, hcs_gold data
--   - mol_silver.publication_evidence and publication_evidence_staging
--   - mol_silver.physician_payments, research_grants, agent_quarantine
--   - mol_raw.europepmc_raw, mol_raw.nih_reporter_raw
--   - All meta.data_sources rows for the 30 new sources
--
-- Prerequisites:
--   - Stop all CMS PUF CronJobs and agent CronJobs before running this
--   - Ensure no active SQLMesh runs are in progress
--
-- Run: doppler run -- psql $DATABASE_URL -f src/dk_data/sql/migrations/114_rollback.sql

BEGIN;

-- ============================================================================
-- 1. REVOKE GRANTS (before dropping schemas)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA hcs_silver FROM web_anon;
        REVOKE USAGE ON SCHEMA hcs_silver FROM web_anon;
        REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA hcs_gold FROM web_anon;
        REVOKE USAGE ON SCHEMA hcs_gold FROM web_anon;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA hcs_silver FROM analyst;
        REVOKE USAGE ON SCHEMA hcs_silver FROM analyst;
        REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA hcs_gold FROM analyst;
        REVOKE USAGE ON SCHEMA hcs_gold FROM analyst;
    END IF;
END
$$;

-- ============================================================================
-- 2. DROP HCS AGENT TABLES (if 086 ran → hcs_agents; if only 085 → hcs_silver)
-- ============================================================================

DROP TABLE IF EXISTS hcs_agents.service_lines CASCADE;
DROP TABLE IF EXISTS hcs_agents.idn_hierarchy CASCADE;
DROP TABLE IF EXISTS hcs_agents.referral_network CASCADE;
DROP TABLE IF EXISTS hcs_agents.verified_contacts CASCADE;
DROP TABLE IF EXISTS hcs_agents.staffing_decomposition CASCADE;
DROP TABLE IF EXISTS hcs_agents.equipment_inventory CASCADE;
-- Fallback: if 086 has not run yet, tables are still in hcs_silver
DROP TABLE IF EXISTS hcs_silver.service_lines CASCADE;
DROP TABLE IF EXISTS hcs_silver.idn_hierarchy CASCADE;
DROP TABLE IF EXISTS hcs_silver.referral_network CASCADE;
DROP TABLE IF EXISTS hcs_silver.verified_contacts CASCADE;
DROP TABLE IF EXISTS hcs_silver.staffing_decomposition CASCADE;
DROP TABLE IF EXISTS hcs_silver.equipment_inventory CASCADE;

-- ============================================================================
-- 3. DROP MOL/AGENT NEW TABLES
-- ============================================================================

-- publication_evidence staging first (staging → live dependency)
-- If 086 ran → mol_agents; if only 085 → mol_silver
DROP TABLE IF EXISTS mol_agents.publication_evidence_staging CASCADE;
DROP TABLE IF EXISTS mol_silver.publication_evidence_staging CASCADE;
DROP TABLE IF EXISTS mol_silver.publication_evidence CASCADE;
DROP TABLE IF EXISTS mol_silver.physician_payments CASCADE;
DROP TABLE IF EXISTS mol_silver.research_grants CASCADE;
-- quarantine: if 086 ran → agents; if only 085 → mol_silver
DROP TABLE IF EXISTS agents.agent_quarantine CASCADE;
DROP TABLE IF EXISTS mol_silver.agent_quarantine CASCADE;
DROP TABLE IF EXISTS mol_silver.drug_spending CASCADE;

-- ============================================================================
-- 4. DROP MOL_RAW NEW API SOURCE TABLES
-- ============================================================================

DROP TABLE IF EXISTS mol_raw.europepmc_raw CASCADE;
DROP TABLE IF EXISTS mol_raw.nih_reporter_raw CASCADE;

-- ============================================================================
-- 5. DROP ALL HCS_RAW TABLES (21 additional)
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_medicare_advantage CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_medicaid_drug_spending CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_dme_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_home_health CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hospice_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_snf_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_outpatient_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_referring_providers CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_ordering_providers CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_lab_services CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_imaging_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_mental_health_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_opioid_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_telehealth_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_geographic_variation CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_chronic_conditions CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_dual_eligible CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_enrollment_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_claim_type_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_utilization_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_cost_reports_puf CASCADE;

-- ============================================================================
-- 6. DROP HCS_RAW CORE 7 TABLES
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_part_d_spending CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_part_b_spending CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_open_payments CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_nppes CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_inpatient_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_physician_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hospital_general_info CASCADE;

-- ============================================================================
-- 7. DROP HCS SCHEMAS (CASCADE drops any remaining objects)
-- ============================================================================

DROP SCHEMA IF EXISTS hcs_gold CASCADE;
DROP SCHEMA IF EXISTS hcs_silver CASCADE;
DROP SCHEMA IF EXISTS hcs_bronze CASCADE;
DROP SCHEMA IF EXISTS hcs_raw CASCADE;

-- ============================================================================
-- 8. DELETE NEW meta.data_sources ROWS (30 rows)
-- ============================================================================

DELETE FROM meta.data_sources
WHERE source_name IN (
    'cms_part_d_spending', 'cms_part_b_spending', 'cms_open_payments',
    'cms_nppes', 'cms_inpatient_puf', 'cms_physician_puf', 'cms_hospital_general_info',
    'cms_medicare_advantage', 'cms_medicaid_drug_spending', 'cms_dme_puf',
    'cms_home_health', 'cms_hospice_puf', 'cms_snf_puf', 'cms_outpatient_puf',
    'cms_referring_providers', 'cms_ordering_providers', 'cms_lab_services',
    'cms_imaging_puf', 'cms_mental_health_puf', 'cms_opioid_puf', 'cms_telehealth_puf',
    'cms_geographic_variation', 'cms_chronic_conditions', 'cms_dual_eligible',
    'cms_enrollment_puf', 'cms_claim_type_puf', 'cms_utilization_puf', 'cms_cost_reports_puf',
    'europepmc', 'nih_reporter'
);

-- ============================================================================
-- 9. NOTES: MANUAL STEPS AFTER ROLLBACK
-- ============================================================================
-- After running this rollback:
-- 1. Revert publications.sql EuropePMC CTE (T058): remove the europepmc_pubs CTE
--    from src/dk_data/sqlmesh/models/molecules/silver/publications.sql
-- 2. Revert trial_outcomes.sql grain change (T039): restore xenon.publication_evidence
--    reference and original grain (molecule_id, trial_nct_id, evidence_source)
-- 3. Remove hcs_silver and hcs_gold from PGRST_DB_SCHEMAS in PostgREST configmap (T016)
-- 4. Remove hcs_* schema mappings from sqlmesh/config.yaml (T060)
-- 5. Remove openai>=1.0.0 from pyproject.toml (T064) if no other code uses it
-- 6. Revert validate-staging-ingestion.sh to SOURCES count check of 22 (T061)

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 114 rollback complete.';
    RAISE NOTICE 'Dropped: hcs_raw, hcs_bronze, hcs_silver, hcs_gold schemas';
    RAISE NOTICE 'Dropped: mol_silver.publication_evidence, publication_evidence_staging';
    RAISE NOTICE 'Dropped: mol_silver.physician_payments, research_grants, agent_quarantine';
    RAISE NOTICE 'Dropped: mol_raw.europepmc_raw, nih_reporter_raw';
    RAISE NOTICE 'Deleted: 30 new meta.data_sources rows';
    RAISE NOTICE 'See notes section for manual revert steps.';
END
$$;

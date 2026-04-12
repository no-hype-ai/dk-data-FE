-- Migration 166: Seed meta.backfill_state with ALL 103 data sources
-- Source: github issue #256 + full fetcher inventory
--
-- Every fetcher in src/dk_data/ingestion/fetchers/*.py gets a row so the
-- orchestrator provides a SINGLE dashboard for the entire data estate.
--
-- Sources that don't need active backfill start as 'complete'; sources that
-- need historical depth extension start as 'paused' (operator flips to 'active').
--
-- Priority bands:
--   10 — high-value gap fixes (clinicaltrials, pubmed, patents)
--   20 — medium gaps (europepmc, openalex, sec_edgar)
--   30 — checkpoint resumes (chembl_activities, pubchem, npi_registry)
--   40 — CMS multi-year extensions (5yr from 3yr)
--   50 — small one-shot loads (purple_book, cms_ddinter, etc.)
--   60 — literature 1-year catch-up
--   90 — already-complete reference / regulatory (no backfill action)

BEGIN;

-- ============================================================================
-- PRIORITY 10 — HIGH-VALUE GAP FIXES (need historical depth extension)
-- ============================================================================
INSERT INTO meta.backfill_state (source_name, fetcher_args, category, expected_min_rows, expected_window_label, priority, status, notes) VALUES
('clinicaltrials',    ARRAY['--days-back','5475'], 'clinical',   50000,     '15 years',  10, 'active', '#256: 5.8K→50K pages. Drug dev cycles need 10-15yr.'),
('pubmed',            ARRAY['--days-back','3650'], 'literature', 500000,    '10 years',  10, 'active', '#256: 0→500K. Schema fix deployed.'),
('uspto_patents',     ARRAY['--days-back','7300'], 'patents',    200000,    '20 years',  10, 'active', '#256: 0→200K. Patent life = 20yr.'),
('uspto_ci',          ARRAY['--days-back','7300'], 'patents',    100000,    '20 years',  10, 'active', '#256: query-scoped CI patents.'),
('epo_ops',           ARRAY['--days-back','7300'], 'patents',    100000,    '20 years',  10, 'active', '#256: 11K→100K. EPO 20yr pharma.')
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- PRIORITY 20 — MEDIUM GAPS
-- ============================================================================
INSERT INTO meta.backfill_state (source_name, fetcher_args, category, expected_min_rows, expected_window_label, priority, status, notes) VALUES
('europepmc',         ARRAY['--days-back','3650'], 'literature', 2000000,   '10 years',  20, 'active', '#256: 530K→2M.'),
('openalex_ci',       ARRAY['--days-back','3650'], 'literature', 5000000,   '10 years',  20, 'active', '#256: 1M→5M.'),
('nih_reporter',      ARRAY['--days-back','3650'], 'literature', 2000000,   '10 years',  20, 'active', '#256: 554K→2M.'),
('sec_edgar',         ARRAY['--days-back','3650'], 'patents',    20000,     '10 years',  20, 'active', '#256: 2K→20K.'),
('uspto_trademarks',  ARRAY['--days-back','7300'], 'patents',    50000,     '20 years',  20, 'active', '#256: 457d→20yr.'),
('euipo_trademarks',  ARRAY['--days-back','3650'], 'patents',    50000,     '10 years',  20, 'active', '#256: 457d→10yr.'),
('euipo_designs',     ARRAY['--days-back','3650'], 'patents',    25000,     '10 years',  20, 'active', '#256: 457d→10yr.')
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- PRIORITY 30 — CHECKPOINT RESUMES (stalled mid-run; just need clean ticks)
-- ============================================================================
INSERT INTO meta.backfill_state (source_name, fetcher_args, category, expected_min_rows, expected_window_label, priority, status, notes) VALUES
('chembl_activities', ARRAY[]::TEXT[], 'reference', 24000000,  'resume from checkpoint 18.3M', 30, 'active', '#256: stalled at 18.3M/24.3M.'),
('pubchem',           ARRAY[]::TEXT[], 'reference', 123000000, 'resume from CID 65M',          30, 'active', '#256: 39M→123M. Shard crons handle bulk.'),
('npi_registry',      ARRAY[]::TEXT[], 'reference', 8000000,   'resume from 2.2M',             30, 'active', '#256: 4M→8M.'),
('kegg_drug',         ARRAY[]::TEXT[], 'reference', 12000,     'resume',                        30, 'active', '#256: 1283→12K.')
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- PRIORITY 40 — CMS PUF MULTI-YEAR EXTENSIONS (3yr → 5yr)
-- These are the largest WAL-per-chunk sources. The fetcher_args point to the
-- FIRST new year to add; operator advances to the next year after each completes.
-- ============================================================================
INSERT INTO meta.backfill_state (source_name, fetcher_args, category, expected_min_rows, expected_window_label, priority, status, notes) VALUES
('cms_open_payments',          ARRAY['--fiscal-year','2019'], 'cms', 50000000, '5yr (add 2019-2020)', 40, 'active', '#256: 2M→50M.'),
('cms_part_d_prescriber',      ARRAY['--fiscal-year','2019'], 'cms', 25000000, '5yr',                 40, 'active', '#256: 3M→25M.'),
('cms_opioid_puf',             ARRAY['--fiscal-year','2019'], 'cms', 40000000, '5yr',                 40, 'active', '#256: 24M→40M.'),
('cms_telehealth_puf',         ARRAY['--fiscal-year','2019'], 'cms', 15000000, '5yr',                 40, 'active', '#256: 9.3M→15M.'),
('cms_physician_puf_services', ARRAY['--fiscal-year','2019'], 'cms', 15000000, '5yr',                 40, 'active', '#256: 9.7M→15M.'),
('cms_inpatient_puf',          ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256 "all other CMS PUFs +60%".'),
('cms_outpatient_puf',         ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_dme_puf',                ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_imaging_puf',            ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_lab_services',           ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_home_health',            ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_hospice_puf',            ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_snf_puf',                ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_part_b_spending',        ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_part_d_spending',        ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_mental_health_puf',      ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_utilization_puf',        ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_medicare_advantage',     ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_claim_type_puf',         ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_dual_eligible',          ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_enrollment_puf',         ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_referring_providers',    ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_ordering_providers',     ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_physician_puf',          ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_geographic_variation',   ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.'),
('cms_medicaid_drug_spending', ARRAY['--fiscal-year','2019'], 'cms', NULL,     '5yr',                 40, 'active', '#256.')
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- PRIORITY 50 — SMALL ONE-SHOT LOADS (fetchers that never ran or need a kick)
-- ============================================================================
INSERT INTO meta.backfill_state (source_name, fetcher_args, category, expected_min_rows, expected_window_label, priority, status, notes) VALUES
('purple_book',               ARRAY[]::TEXT[], 'regulatory', 4000,   'one-shot', 50, 'active', '#256: 0→4K. Never triggered.'),
('fda_ndc',                   ARRAY[]::TEXT[], 'regulatory', 133000, 'one-shot', 50, 'active', '#256: 0→133K. Lucene bug fixed.'),
('fda_rems',                  ARRAY[]::TEXT[], 'regulatory', 200,    'one-shot', 50, 'active', '#256: remove max_records.'),
('cms_chronic_conditions',    ARRAY['--fiscal-year','2023'], 'cms', 5000,   'one-shot', 50, 'active', '#256: 0→5K.'),
('cms_hospital_general_info', ARRAY[]::TEXT[], 'cms',        5000,   'one-shot', 50, 'active', '#256: 0→5K.'),
('cms_ddinter',               ARRAY[]::TEXT[], 'cms',        1000,   'one-shot', 50, 'active', '#256: 0→1K.'),
('imgt',                      ARRAY[]::TEXT[], 'reference',  5000,   'one-shot', 50, 'active', '#256: 0→5K. Bulk FASTA fix deployed.'),
('nice_hta',                  ARRAY[]::TEXT[], 'regulatory', 4000,   'one-shot', 50, 'active', '#256: 0→4K.'),
('acc_tvc',                   ARRAY[]::TEXT[], 'reference',  500,    'one-shot', 50, 'active', '#256: 0→500. Cronjob added.'),
('hta_bodies',                ARRAY[]::TEXT[], 'regulatory', 4000,   'one-shot', 50, 'active', '#256: HTA body directory.'),
('cochrane',                  ARRAY[]::TEXT[], 'reference',  10000,  'all time', 50, 'active', '#256: remove max_records cap.')
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- PRIORITY 60 — LITERATURE 1-YEAR CATCH-UP
-- ============================================================================
INSERT INTO meta.backfill_state (source_name, fetcher_args, category, expected_min_rows, expected_window_label, priority, status, notes) VALUES
('journal_rss',    ARRAY[]::TEXT[],            'literature', NULL, 'one-shot', 60, 'active', 'RSS feeds only expose recent articles. --days-back is ignored by the fetcher.'),
('medical_news',   ARRAY['--days-back','365'], 'literature', NULL, '1 year',  60, 'active', 'News only recent.')
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- PRIORITY 90 — ALREADY-COMPLETE / MANAGED BY DAILY FETCHER CRON
-- These are here so meta.backfill_progress shows 100% coverage of the estate.
-- status='complete' means the orchestrator will never pick them unless an
-- operator explicitly flips them to 'active'.
-- ============================================================================
INSERT INTO meta.backfill_state (source_name, fetcher_args, category, expected_min_rows, expected_window_label, priority, status, notes) VALUES
-- Reference databases: full corpus, no date filter needed
('bindingdb',         ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by daily/weekly fetcher cron.'),
('cdc_vaccines',      ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by cron.'),
('chembl_molecules',  ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
('dailymed',          ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by cron.'),
('drugbank',          ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
('orcid',             ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by weekly cron.'),
('pdb',               ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by cron.'),
('pharmgkb',          ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by cron.'),
('reactome',          ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
('rxnorm',            ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
('sider',             ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
('tdc_admet',         ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
('ttd',               ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
('uniprot',           ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by weekly cron.'),
('who_gho',           ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by cron.'),
('who_icd',           ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by cron.'),
('who_inn',           ARRAY[]::TEXT[], 'reference',  NULL, 'full corpus', 90, 'complete', 'Managed by monthly cron.'),
-- Regulatory: all-time, managed by daily/weekly fetcher cron
('fda_drugs',         ARRAY[]::TEXT[], 'regulatory', NULL, 'all time', 90, 'complete', 'Managed by cron. #256: remove max_records only.'),
('orange_book',       ARRAY[]::TEXT[], 'regulatory', NULL, 'all time', 90, 'complete', 'Managed by monthly cron.'),
('openfda_labels',    ARRAY[]::TEXT[], 'regulatory', NULL, 'all time', 90, 'complete', 'Managed by weekly cron. Year-partitioned.'),
('openfda_faers',     ARRAY[]::TEXT[], 'regulatory', NULL, 'all time', 90, 'complete', 'Managed by weekly cron. Year-partitioned.'),
('ema_mol',           ARRAY[]::TEXT[], 'regulatory', NULL, 'all time', 90, 'complete', 'Managed by monthly cron.'),
('ema_regulatory',    ARRAY[]::TEXT[], 'regulatory', NULL, 'all time', 90, 'complete', 'Managed by weekly cron.'),
('hrsa',              ARRAY[]::TEXT[], 'reference',  NULL, 'all time', 90, 'complete', 'Managed by cron.'),
-- CMS operational: latest-only, managed by daily/weekly fetcher cron
('cms_care_compare',       ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Latest facility data only.'),
('cms_chow',               ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by monthly cron.'),
('cms_cost_reports',       ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_cost_reports_puf',   ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_coverage',           ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_dmepos',             ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_formulary',          ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_hcris',              ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_hospital_affiliation', ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_hospital_info',      ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_hospital_quality',   ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_inpatient',          ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_magnet',             ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_medicare',           ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_ndc',                ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_nppes',              ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_nucc',               ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_pecos',              ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_pos',                ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_post_acute',         ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_puf',                ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Umbrella PUF script.'),
('cms_rbcs',               ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_stabilis',           ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.'),
('cms_usp',                ARRAY[]::TEXT[], 'cms', NULL, 'latest', 90, 'complete', 'Managed by cron.')
ON CONFLICT (source_name) DO NOTHING;

COMMIT;

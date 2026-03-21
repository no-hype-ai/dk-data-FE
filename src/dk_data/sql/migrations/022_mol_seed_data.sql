-- Migration: 022_mol_seed_data.sql
-- Feature: 012-dk-data-platform
-- Description: Seed data for molecule platform data sources and batch jobs
-- Date: 2026-01-27

-- =============================================================================
-- DATA SOURCES - Molecule Platform Sources
-- =============================================================================

INSERT INTO meta.ops_data_sources (
    source_name,
    source_type,
    source_url,
    description,
    refresh_frequency,
    is_active,
    topic_tags,
    staleness_threshold_hours,
    target_tables
) VALUES
    -- Primary molecule data sources
    (
        'chembl',
        'api',
        'https://www.ebi.ac.uk/chembl/api/data',
        'ChEMBL database - curated bioactive molecules with drug-like properties',
        'monthly',
        TRUE,
        ARRAY['molecules', 'bioactivity', 'drug-discovery'],
        720,  -- 30 days
        ARRAY['mol_raw.chembl', 'mol_bronze.chembl']
    ),
    (
        'pubchem',
        'api',
        'https://pubchem.ncbi.nlm.nih.gov/rest/pug',
        'PubChem compound database - chemical structures and properties',
        'monthly',
        TRUE,
        ARRAY['molecules', 'chemical-structures', 'identifiers'],
        720,
        ARRAY['mol_raw.pubchem', 'mol_bronze.pubchem']
    ),
    (
        'drugbank',
        'api',
        'https://go.drugbank.com/releases/latest',
        'DrugBank - comprehensive drug database with clinical information',
        'quarterly',
        TRUE,
        ARRAY['molecules', 'drugs', 'clinical', 'pharmacology'],
        2160,  -- 90 days
        ARRAY['mol_raw.drugbank', 'mol_bronze.drugbank']
    ),
    (
        'clinicaltrials',
        'api',
        'https://clinicaltrials.gov/api/v2/studies',
        'ClinicalTrials.gov - clinical trial registry',
        'daily',
        TRUE,
        ARRAY['clinical-trials', 'drug-development', 'regulatory'],
        24,
        ARRAY['mol_raw.clinicaltrials', 'mol_bronze.clinicaltrials']
    ),
    (
        'openfda_labels',
        'api',
        'https://api.fda.gov/drug/label.json',
        'OpenFDA Drug Labels - FDA-approved drug labeling',
        'daily',
        TRUE,
        ARRAY['drug-labels', 'fda', 'regulatory', 'safety'],
        24,
        ARRAY['mol_raw.openfda_labels', 'mol_bronze.openfda_labels']
    ),
    (
        'openfda_faers',
        'api',
        'https://api.fda.gov/drug/event.json',
        'OpenFDA FAERS - FDA Adverse Event Reporting System',
        'weekly',
        TRUE,
        ARRAY['adverse-events', 'safety', 'faers', 'pharmacovigilance'],
        168,  -- 7 days
        ARRAY['mol_raw.openfda_faers', 'mol_bronze.openfda_faers']
    ),
    (
        'sider',
        'file',
        'http://sideeffects.embl.de/download/',
        'SIDER - Side Effect Resource (known drug side effects)',
        'quarterly',
        TRUE,
        ARRAY['side-effects', 'safety', 'adverse-events'],
        2160,
        ARRAY['mol_raw.sider', 'mol_bronze.sider']
    ),
    (
        'uniprot',
        'api',
        'https://rest.uniprot.org/uniprotkb',
        'UniProt - protein sequence and function database',
        'monthly',
        TRUE,
        ARRAY['proteins', 'targets', 'sequences'],
        720,
        ARRAY['mol_raw.uniprot']
    ),
    (
        'openalex',
        'api',
        'https://api.openalex.org',
        'OpenAlex - open catalog of scholarly works',
        'weekly',
        TRUE,
        ARRAY['publications', 'literature', 'citations'],
        168,
        ARRAY['mol_raw.openalex']
    )
ON CONFLICT (source_name) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    description = EXCLUDED.description,
    refresh_frequency = EXCLUDED.refresh_frequency,
    topic_tags = EXCLUDED.topic_tags,
    staleness_threshold_hours = EXCLUDED.staleness_threshold_hours,
    target_tables = EXCLUDED.target_tables;

-- =============================================================================
-- BATCH JOBS - Molecule Pipeline Jobs
-- =============================================================================

INSERT INTO meta.ops_batch_jobs (
    job_name,
    description,
    cron_schedule,
    is_enabled
) VALUES
    -- Molecule fetch jobs
    (
        'fetch-chembl',
        'Fetch molecule data from ChEMBL API',
        '0 2 1 * *',  -- Monthly on 1st at 2 AM
        TRUE
    ),
    (
        'fetch-pubchem',
        'Fetch compound data from PubChem API',
        '0 3 1 * *',  -- Monthly on 1st at 3 AM
        TRUE
    ),
    (
        'fetch-clinicaltrials',
        'Fetch clinical trial data from ClinicalTrials.gov',
        '0 1 * * *',  -- Daily at 1 AM
        TRUE
    ),
    (
        'fetch-openfda-labels',
        'Fetch drug label data from OpenFDA',
        '0 2 * * *',  -- Daily at 2 AM
        TRUE
    ),
    (
        'fetch-openfda-faers',
        'Fetch adverse event data from OpenFDA FAERS',
        '0 3 * * 0',  -- Weekly on Sunday at 3 AM
        TRUE
    ),
    (
        'fetch-sider',
        'Fetch side effect data from SIDER',
        '0 4 1 */3 *',  -- Quarterly on 1st at 4 AM
        TRUE
    ),
    -- Molecule transform jobs
    (
        'mol-bronze-transform',
        'Transform raw molecule data to bronze layer',
        '0 6 * * *',  -- Daily at 6 AM
        TRUE
    ),
    (
        'mol-silver-transform',
        'Transform bronze to silver with entity resolution',
        '0 7 * * *',  -- Daily at 7 AM
        TRUE
    ),
    (
        'mol-gold-aggregate',
        'Aggregate silver data into gold profiles',
        '0 8 * * *',  -- Daily at 8 AM
        TRUE
    ),
    -- Full molecule pipeline
    (
        'mol-pipeline-full',
        'Run complete molecule data pipeline (fetch -> transform -> aggregate)',
        '0 0 * * 0',  -- Weekly on Sunday at midnight
        TRUE
    )
ON CONFLICT (job_name) DO UPDATE SET
    description = EXCLUDED.description,
    cron_schedule = EXCLUDED.cron_schedule;

-- Link batch jobs to data sources
UPDATE meta.ops_batch_jobs SET source_ids = (
    SELECT ARRAY_AGG(source_id)
    FROM meta.ops_data_sources
    WHERE source_name = 'chembl'
) WHERE job_name = 'fetch-chembl';

UPDATE meta.ops_batch_jobs SET source_ids = (
    SELECT ARRAY_AGG(source_id)
    FROM meta.ops_data_sources
    WHERE source_name = 'pubchem'
) WHERE job_name = 'fetch-pubchem';

UPDATE meta.ops_batch_jobs SET source_ids = (
    SELECT ARRAY_AGG(source_id)
    FROM meta.ops_data_sources
    WHERE source_name = 'clinicaltrials'
) WHERE job_name = 'fetch-clinicaltrials';

UPDATE meta.ops_batch_jobs SET source_ids = (
    SELECT ARRAY_AGG(source_id)
    FROM meta.ops_data_sources
    WHERE source_name = 'openfda_labels'
) WHERE job_name = 'fetch-openfda-labels';

UPDATE meta.ops_batch_jobs SET source_ids = (
    SELECT ARRAY_AGG(source_id)
    FROM meta.ops_data_sources
    WHERE source_name = 'openfda_faers'
) WHERE job_name = 'fetch-openfda-faers';

UPDATE meta.ops_batch_jobs SET source_ids = (
    SELECT ARRAY_AGG(source_id)
    FROM meta.ops_data_sources
    WHERE source_name = 'sider'
) WHERE job_name = 'fetch-sider';

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Molecule seed data migration complete (022_mol_seed_data.sql)';
    RAISE NOTICE 'Data sources added: chembl, pubchem, drugbank, clinicaltrials, openfda_labels, openfda_faers, sider, uniprot, openalex';
    RAISE NOTICE 'Batch jobs added: fetch-chembl, fetch-pubchem, fetch-clinicaltrials, fetch-openfda-labels, fetch-openfda-faers, fetch-sider, mol-bronze-transform, mol-silver-transform, mol-gold-aggregate, mol-pipeline-full';
END
$$;

-- Seed data for meta.batch_jobs
-- Feature: 001-data-layer-postgrest-gitops
-- Task: T020
--
-- Initial batch job definitions for the TAVR data platform

-- First, get source_ids dynamically based on source_name
DO $$
DECLARE
    v_cms_inpatient_id INTEGER;
    v_cms_hospital_id INTEGER;
    v_cms_cost_id INTEGER;
    v_acc_tvc_id INTEGER;
    v_hrsa_id INTEGER;
    v_bindingdb_id INTEGER;
    v_orange_book_id INTEGER;
    v_sider_id INTEGER;
    v_tdc_admet_id INTEGER;
    v_ema_id INTEGER;
    v_rxnorm_id INTEGER;
    v_dailymed_id INTEGER;
    v_fda_drugs_id INTEGER;
    v_kegg_drug_id INTEGER;
    v_ttd_id INTEGER;
    v_pharmgkb_id INTEGER;
    v_imgt_id INTEGER;
    v_cdc_vaccines_id INTEGER;
    v_pubmed_id INTEGER;
    v_openalex_ci_id INTEGER;
    v_ema_regulatory_id INTEGER;
    v_drugbank_id INTEGER;
    v_uspto_patents_id INTEGER;
    v_journal_rss_id INTEGER;
    v_uspto_ci_id INTEGER;
    v_hta_bodies_id INTEGER;
    v_epo_ops_id INTEGER;
    v_cochrane_id INTEGER;
    v_medical_news_id INTEGER;
    v_sec_edgar_id INTEGER;
BEGIN
    -- Get source IDs
    SELECT source_id INTO v_cms_inpatient_id FROM meta.data_sources WHERE source_name = 'cms_medicare_inpatient';
    SELECT source_id INTO v_cms_hospital_id FROM meta.data_sources WHERE source_name = 'cms_hospital_info';
    SELECT source_id INTO v_cms_cost_id FROM meta.data_sources WHERE source_name = 'cms_cost_reports';
    SELECT source_id INTO v_acc_tvc_id FROM meta.data_sources WHERE source_name = 'acc_tvc';
    SELECT source_id INTO v_hrsa_id FROM meta.data_sources WHERE source_name = 'hrsa_shortage_areas';
    SELECT source_id INTO v_bindingdb_id FROM meta.data_sources WHERE source_name = 'bindingdb';
    SELECT source_id INTO v_orange_book_id FROM meta.data_sources WHERE source_name = 'orange_book';
    SELECT source_id INTO v_sider_id FROM meta.data_sources WHERE source_name = 'sider';
    SELECT source_id INTO v_tdc_admet_id FROM meta.data_sources WHERE source_name = 'tdc_admet';
    SELECT source_id INTO v_ema_id FROM meta.data_sources WHERE source_name = 'ema';
    SELECT source_id INTO v_rxnorm_id FROM meta.data_sources WHERE source_name = 'rxnorm';
    SELECT source_id INTO v_dailymed_id FROM meta.data_sources WHERE source_name = 'dailymed';
    SELECT source_id INTO v_fda_drugs_id FROM meta.data_sources WHERE source_name = 'fda_drugs';
    SELECT source_id INTO v_kegg_drug_id FROM meta.data_sources WHERE source_name = 'kegg_drug';
    SELECT source_id INTO v_ttd_id FROM meta.data_sources WHERE source_name = 'ttd';
    SELECT source_id INTO v_pharmgkb_id FROM meta.data_sources WHERE source_name = 'pharmgkb';
    SELECT source_id INTO v_imgt_id FROM meta.data_sources WHERE source_name = 'imgt';
    SELECT source_id INTO v_cdc_vaccines_id FROM meta.data_sources WHERE source_name = 'cdc_vaccines';
    SELECT source_id INTO v_pubmed_id FROM meta.data_sources WHERE source_name = 'pubmed';
    SELECT source_id INTO v_openalex_ci_id FROM meta.data_sources WHERE source_name = 'openalex_ci';
    SELECT source_id INTO v_ema_regulatory_id FROM meta.data_sources WHERE source_name = 'ema_regulatory';
    SELECT source_id INTO v_drugbank_id FROM meta.data_sources WHERE source_name = 'drugbank';
    SELECT source_id INTO v_uspto_patents_id FROM meta.data_sources WHERE source_name = 'uspto_patents';
    SELECT source_id INTO v_journal_rss_id FROM meta.data_sources WHERE source_name = 'journal_rss';
    SELECT source_id INTO v_uspto_ci_id FROM meta.data_sources WHERE source_name = 'uspto_ci';
    SELECT source_id INTO v_hta_bodies_id FROM meta.data_sources WHERE source_name = 'hta_bodies';
    SELECT source_id INTO v_epo_ops_id FROM meta.data_sources WHERE source_name = 'epo_ops';
    SELECT source_id INTO v_cochrane_id FROM meta.data_sources WHERE source_name = 'cochrane';
    SELECT source_id INTO v_medical_news_id FROM meta.data_sources WHERE source_name = 'medical_news';
    SELECT source_id INTO v_sec_edgar_id FROM meta.data_sources WHERE source_name = 'sec_edgar';

    -- Job 1: fetch-cms-all - Fetches all CMS data sources
    INSERT INTO meta.batch_jobs (
        job_name,
        description,
        cron_schedule,
        source_ids,
        is_enabled,
        next_scheduled_run
    ) VALUES (
        'fetch-cms-all',
        'Fetch all CMS data sources (Medicare Inpatient, Hospital Info, Cost Reports)',
        '0 2 * * 0',  -- Every Sunday at 2 AM
        ARRAY[v_cms_inpatient_id, v_cms_hospital_id, v_cms_cost_id],
        TRUE,
        NOW() + INTERVAL '1 week'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        cron_schedule = EXCLUDED.cron_schedule,
        source_ids = EXCLUDED.source_ids;

    -- Job 2: fetch-cms-hospitals - Individual CMS Hospital Info fetch
    INSERT INTO meta.batch_jobs (
        job_name,
        description,
        cron_schedule,
        source_ids,
        is_enabled,
        next_scheduled_run
    ) VALUES (
        'fetch-cms-hospitals',
        'Fetch CMS Hospital General Information (demographics, ownership, ratings)',
        '0 3 1 * *',  -- 1st of each month at 3 AM
        ARRAY[v_cms_hospital_id],
        TRUE,
        NOW() + INTERVAL '1 month'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        cron_schedule = EXCLUDED.cron_schedule,
        source_ids = EXCLUDED.source_ids;

    -- Job 3: fetch-cms-inpatient - Individual CMS Medicare Inpatient fetch
    INSERT INTO meta.batch_jobs (
        job_name,
        description,
        cron_schedule,
        source_ids,
        is_enabled,
        next_scheduled_run
    ) VALUES (
        'fetch-cms-inpatient',
        'Fetch CMS Medicare Inpatient data (TAVR DRG 266/267 volumes)',
        '0 3 1 */3 *',  -- 1st of Jan, Apr, Jul, Oct at 3 AM
        ARRAY[v_cms_inpatient_id],
        TRUE,
        NOW() + INTERVAL '3 months'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        cron_schedule = EXCLUDED.cron_schedule,
        source_ids = EXCLUDED.source_ids;

    -- Job 4: fetch-acc-tvc - ACC TVC Certification fetch
    INSERT INTO meta.batch_jobs (
        job_name,
        description,
        cron_schedule,
        source_ids,
        is_enabled,
        next_scheduled_run
    ) VALUES (
        'fetch-acc-tvc',
        'Fetch ACC Transcatheter Valve Certification data',
        '0 4 1 */3 *',  -- Quarterly on 1st at 4 AM
        ARRAY[v_acc_tvc_id],
        TRUE,
        NOW() + INTERVAL '3 months'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        cron_schedule = EXCLUDED.cron_schedule,
        source_ids = EXCLUDED.source_ids;

    -- Job 5: fetch-hrsa - HRSA Shortage Areas fetch
    INSERT INTO meta.batch_jobs (
        job_name,
        description,
        cron_schedule,
        source_ids,
        is_enabled,
        next_scheduled_run
    ) VALUES (
        'fetch-hrsa',
        'Fetch HRSA Health Professional Shortage Area designations',
        '0 5 15 * *',  -- 15th of each month at 5 AM
        ARRAY[v_hrsa_id],
        TRUE,
        NOW() + INTERVAL '1 month'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        cron_schedule = EXCLUDED.cron_schedule,
        source_ids = EXCLUDED.source_ids;

    -- Job 6: catalog-refresh - Refresh catalog metadata
    INSERT INTO meta.batch_jobs (
        job_name,
        description,
        cron_schedule,
        source_ids,
        is_enabled,
        next_scheduled_run
    ) VALUES (
        'catalog-refresh',
        'Refresh data catalog semantic metadata (descriptions, topic_tags, ai_description)',
        '0 6 * * *',  -- Daily at 6 AM
        ARRAY[]::INTEGER[],  -- No specific sources - affects all
        TRUE,
        NOW() + INTERVAL '1 day'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        cron_schedule = EXCLUDED.cron_schedule;

    -- Job 7: sqlmesh-run - Run SQLMesh transformations
    INSERT INTO meta.batch_jobs (
        job_name,
        description,
        cron_schedule,
        source_ids,
        is_enabled,
        next_scheduled_run
    ) VALUES (
        'sqlmesh-run',
        'Run SQLMesh transformations to populate staging and mart tables',
        '0 7 * * *',  -- Daily at 7 AM (after catalog-refresh)
        ARRAY[]::INTEGER[],  -- Transforms all sources
        TRUE,
        NOW() + INTERVAL '1 day'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        cron_schedule = EXCLUDED.cron_schedule;

    -- Job 8: mol-fetch-weekly - Weekly molecule data fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'mol-fetch-weekly',
        'Fetch weekly molecule data (OpenFDA, ChEMBL, PubChem, EMA, Orange Book)',
        '0 3 * * 0',
        ARRAY[v_ema_id, v_orange_book_id],
        TRUE,
        NOW() + INTERVAL '1 week'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 9: mol-fetch-monthly - Monthly molecule data fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'mol-fetch-monthly',
        'Fetch monthly molecule data (BindingDB, SIDER, TDC ADMET, plus Tier 3 sources)',
        '0 8 1 * *',
        ARRAY[v_bindingdb_id, v_sider_id, v_tdc_admet_id, v_rxnorm_id, v_dailymed_id, v_fda_drugs_id, v_kegg_drug_id, v_ttd_id, v_pharmgkb_id, v_imgt_id, v_cdc_vaccines_id],
        TRUE,
        NOW() + INTERVAL '1 month'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 10: fetch-pubmed - Daily PubMed CI fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-pubmed',
        'Fetch PubMed pharmaceutical literature via NCBI E-utilities',
        '0 11 * * *',
        ARRAY[v_pubmed_id],
        TRUE,
        NOW() + INTERVAL '1 day'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 11: fetch-openalex-ci - Daily OpenAlex CI fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-openalex-ci',
        'Fetch OpenAlex pharmaceutical research works for competitive intelligence',
        '0 12 * * *',
        ARRAY[v_openalex_ci_id],
        TRUE,
        NOW() + INTERVAL '1 day'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 12: fetch-ema-regulatory - Weekly EMA regulatory CI fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-ema-regulatory',
        'Fetch EMA regulatory decisions (CHMP opinions, EPARs, safety signals)',
        '0 13 * * 0',
        ARRAY[v_ema_regulatory_id],
        TRUE,
        NOW() + INTERVAL '1 week'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 13: fetch-drugbank - Monthly DrugBank fetch (credential-gated)
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-drugbank',
        'Fetch DrugBank drug data (requires DRUGBANK_API_KEY)',
        '0 17 1 * *',
        ARRAY[v_drugbank_id],
        TRUE,
        NOW() + INTERVAL '1 month'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 14: fetch-uspto-patents - Weekly USPTO Patents fetch (credential-gated)
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-uspto-patents',
        'Fetch USPTO PatentsView pharmaceutical patents',
        '0 17 * * 0',
        ARRAY[v_uspto_patents_id],
        TRUE,
        NOW() + INTERVAL '1 week'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 15: fetch-journal-rss - Daily Journal RSS fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-journal-rss',
        'Fetch journal RSS feeds (NEJM, Lancet, JAMA, BMJ, Nature Medicine)',
        '0 13 * * *',
        ARRAY[v_journal_rss_id],
        TRUE,
        NOW() + INTERVAL '1 day'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 16: fetch-uspto-ci - Weekly USPTO CI fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-uspto-ci',
        'Fetch USPTO PatentsView CI pharma patents with search term scoping',
        '0 14 * * 0',
        ARRAY[v_uspto_ci_id],
        TRUE,
        NOW() + INTERVAL '1 week'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 17: fetch-hta - Weekly HTA Bodies fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-hta',
        'Fetch HTA body decisions (NICE, G-BA, HAS, PBAC)',
        '0 14 * * 0',
        ARRAY[v_hta_bodies_id],
        TRUE,
        NOW() + INTERVAL '1 week'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 18: fetch-epo - Weekly EPO OPS fetch (credential-gated)
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-epo',
        'Fetch EPO Open Patent Services pharma patents',
        '0 15 * * 0',
        ARRAY[v_epo_ops_id],
        TRUE,
        NOW() + INTERVAL '1 week'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 19: fetch-cochrane - Monthly Cochrane fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-cochrane',
        'Fetch Cochrane Library systematic reviews',
        '0 15 1 * *',
        ARRAY[v_cochrane_id],
        TRUE,
        NOW() + INTERVAL '1 month'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 20: fetch-news - Daily Medical News fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-news',
        'Fetch medical news from Medscape, Healio, FiercePharma RSS',
        '0 16 * * *',
        ARRAY[v_medical_news_id],
        TRUE,
        NOW() + INTERVAL '1 day'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    -- Job 21: fetch-sec-edgar - Daily SEC EDGAR fetch
    INSERT INTO meta.batch_jobs (
        job_name, description, cron_schedule, source_ids, is_enabled, next_scheduled_run
    ) VALUES (
        'fetch-sec-edgar',
        'Fetch SEC EDGAR pharma company filings (10-K, 10-Q, 8-K)',
        '0 16 * * *',
        ARRAY[v_sec_edgar_id],
        TRUE,
        NOW() + INTERVAL '1 day'
    )
    ON CONFLICT (job_name) DO UPDATE SET
        description = EXCLUDED.description,
        source_ids = EXCLUDED.source_ids;

    RAISE NOTICE 'Batch jobs seeded successfully';
END $$;

-- Verify seeded jobs
SELECT job_id, job_name, cron_schedule, is_enabled,
       array_length(source_ids, 1) as source_count
FROM meta.batch_jobs
ORDER BY job_name;

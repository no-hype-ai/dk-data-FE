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
BEGIN
    -- Get source IDs
    SELECT source_id INTO v_cms_inpatient_id FROM meta.data_sources WHERE source_name = 'cms_medicare_inpatient';
    SELECT source_id INTO v_cms_hospital_id FROM meta.data_sources WHERE source_name = 'cms_hospital_info';
    SELECT source_id INTO v_cms_cost_id FROM meta.data_sources WHERE source_name = 'cms_cost_reports';
    SELECT source_id INTO v_acc_tvc_id FROM meta.data_sources WHERE source_name = 'acc_tvc';
    SELECT source_id INTO v_hrsa_id FROM meta.data_sources WHERE source_name = 'hrsa_shortage_areas';

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

    RAISE NOTICE 'Batch jobs seeded successfully';
END $$;

-- Verify seeded jobs
SELECT job_id, job_name, cron_schedule, is_enabled,
       array_length(source_ids, 1) as source_count
FROM meta.batch_jobs
ORDER BY job_name;

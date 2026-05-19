-- SQLMesh Model: Silver Clinical Trials
-- Transforms Bronze ClinicalTrials.gov data to normalized Silver layer
-- Part of: 012-dk-data-platform
-- Updated: 019-cms-puf-platform-reconciliation — zero column loss audit pass
--   All bronze columns now promoted; eligibility, locations, results, and oversight
--   columns were previously dropped without justification.
-- Updated: T115+T131 — converted from INCREMENTAL_BY_TIME_RANGE to INCREMENTAL_BY_UNIQUE_KEY
--   (T170), replaced S3 correlated subquery with LEFT JOIN LATERAL, added condition_id
--   linkage via MeSH (FR-032).

MODEL (
    name mol_silver.clinical_trials,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key nct_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (nct_id, title)),
        unique_values(columns := (nct_id))
    ),
    grain nct_id
);

-- Dedup bronze: one row per nct_id, latest request_timestamp wins.
WITH deduped_bronze AS (
    SELECT DISTINCT ON (nct_id)
        *
    FROM mol_bronze.clinicaltrials
    WHERE nct_id IS NOT NULL
    ORDER BY nct_id, request_timestamp DESC
)

SELECT
    gen_random_uuid() AS trial_id,

    -- External Identifiers
    b.nct_id,
    b.org_study_id,
    b.acronym,

    -- Titles (bronze names retained verbatim per FR-001)
    b.brief_title,
    b.official_title,

    -- Summary
    b.brief_summary,
    b.detailed_description,

    -- Status
    b.overall_status,
    b.last_known_status,
    b.why_stopped,

    -- Phase (derived string is a NEW computed column; bronze `phases` retained verbatim)
    CASE
        WHEN b.phases::TEXT LIKE '%PHASE1%' AND b.phases::TEXT LIKE '%PHASE2%' THEN 'Phase 1/2'
        WHEN b.phases::TEXT LIKE '%PHASE2%' AND b.phases::TEXT LIKE '%PHASE3%' THEN 'Phase 2/3'
        WHEN b.phases::TEXT LIKE '%PHASE1%' THEN 'Phase 1'
        WHEN b.phases::TEXT LIKE '%PHASE2%' THEN 'Phase 2'
        WHEN b.phases::TEXT LIKE '%PHASE3%' THEN 'Phase 3'
        WHEN b.phases::TEXT LIKE '%PHASE4%' THEN 'Phase 4'
        WHEN b.phases::TEXT LIKE '%EARLY%' THEN 'Early Phase 1'
        ELSE 'Not Applicable'
    END AS phase_derived,
    b.phases,

    -- Dates
    b.start_date,
    b.completion_date,
    b.primary_completion_date,
    b.first_submit_date,
    b.first_post_date,
    b.last_update_date,

    -- Conditions and Keywords
    b.conditions,
    b.keywords,

    -- Interventions and Arms
    b.interventions,
    b.arm_groups,

    -- Study Design
    b.study_type,
    b.allocation,
    b.intervention_model,
    b.masking,
    b.enrollment_count,
    b.enrollment_type,

    -- Eligibility (previously dropped — restored in 019)
    b.eligibility_sex,
    b.minimum_age,
    b.maximum_age,
    b.healthy_volunteers,
    b.eligibility_criteria,

    -- Sponsors
    b.lead_sponsor_name,
    b.lead_sponsor_class,
    b.collaborators,
    b.responsible_party,

    -- Contacts and Locations (previously dropped — restored in 019)
    b.central_contacts,
    b.locations,

    -- Outcomes
    b.primary_outcomes,
    b.secondary_outcomes,

    -- Results (previously dropped — restored in 019)
    b.has_results,
    b.results_section,

    -- Oversight (extracted directly from raw_json — not in typed bronze columns)
    (b.raw_json->'protocolSection'->'oversightModule'->>'isFdaRegulatedDrug')::BOOLEAN AS fda_regulated_drug,
    (b.raw_json->'protocolSection'->'oversightModule'->>'isFdaRegulatedDevice')::BOOLEAN AS fda_regulated_device,
    (b.raw_json->'protocolSection'->'oversightModule'->>'humanSubjectReviewBoard' = 'Yes')::BOOLEAN AS has_dmc,

    -- Entity resolution: molecule_id via DRUG intervention name match against molecule_names hub.
    -- LEFT JOIN LATERAL replaces S3 correlated subquery (T115).
    -- Matches normalized intervention name to mol_silver.molecule_names.normalized_name.
    mol_interv.molecule_id AS molecule_id,

    -- Condition linkage via MeSH (FR-032): match condition text from bronze conditions array
    -- against ind_silver.condition_names.normalized_name (T131).
    cond_link.condition_id AS condition_id,

    -- Source Tracking
    b.id,
    'clinicaltrials_gov' AS source,
    b.request_timestamp,
    NOW() AS created_at,
    NOW() AS updated_at

FROM deduped_bronze b

-- Tier 1: molecule_id via DRUG intervention name normalized match
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM jsonb_array_elements(COALESCE(b.interventions, '[]'::jsonb)) AS interv
    JOIN mol_silver.molecule_names mn
        ON interv->>'type' = 'DRUG'
        AND mn.normalized_name = LOWER(REGEXP_REPLACE(interv->>'name', '[^a-zA-Z0-9 ]', '', 'g'))
    ORDER BY mn.molecule_id
    LIMIT 1
) mol_interv ON TRUE

-- Condition linkage via MeSH condition names (FR-032)
LEFT JOIN LATERAL (
    SELECT ci.condition_id
    FROM jsonb_array_elements_text(COALESCE(b.conditions, '[]'::jsonb)) AS cond(condition_text)
    JOIN ind_silver.condition_names cn ON cn.normalized_name = LOWER(REGEXP_REPLACE(cond.condition_text, '[^a-zA-Z0-9 ]', '', 'g'))
    JOIN ind_silver.condition_identifiers ci ON ci.condition_id = cn.condition_id
    ORDER BY ci.condition_id
    LIMIT 1
) cond_link ON TRUE;

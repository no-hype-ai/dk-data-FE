-- SQLMesh Model: Gold Molecule Profile
-- Pre-aggregated decision-ready molecule profiles
-- Excludes quarantined records (needs_review=TRUE)
-- Part of: 012-dk-data-platform

MODEL (
    name mol_gold.molecule_profile,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key molecule_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (molecule_id, canonical_name)),
        unique_values(columns := (molecule_id))
    ),
    grain molecule_id
);

WITH molecule_base AS (
    SELECT
        m.molecule_id,
        m.inchi_key,
        m.canonical_name,
        m.canonical_smiles,
        m.inchi,
        m.molecular_formula,
        m.molecular_weight,
        m.molecule_type,
        NULL::TEXT[] AS therapeutic_areas,
        m.mechanism_of_action,
        m.max_phase,
        m.resolution_confidence,
        m.created_at,
        m.updated_at
    FROM mol_silver.molecules m
    WHERE m.needs_review = FALSE  -- Exclude quarantined records
),

-- Get cross-reference identifiers
cross_refs AS (
    SELECT
        molecule_id,
        MAX(CASE WHEN identifier_type = 'drugbank_id' AND is_primary THEN identifier_value END) AS drugbank_id,
        MAX(CASE WHEN identifier_type = 'chembl_id' AND is_primary THEN identifier_value END) AS chembl_id,
        MAX(CASE WHEN identifier_type = 'pubchem_cid' AND is_primary THEN identifier_value::BIGINT END) AS pubchem_cid,
        MAX(CASE WHEN identifier_type = 'unii' AND is_primary THEN identifier_value END) AS unii,
        MAX(CASE WHEN identifier_type = 'cas_number' AND is_primary THEN identifier_value END) AS cas_number,
        MAX(CASE WHEN identifier_type = 'rxcui' AND is_primary THEN identifier_value END) AS rxcui
    FROM mol_silver.identifier_mappings
    GROUP BY molecule_id
),

-- Aggregate aliases
aliases AS (
    SELECT
        molecule_id,
        jsonb_agg(DISTINCT alias_name) AS alias_list
    FROM mol_silver.molecule_aliases
    GROUP BY molecule_id
),

-- Clinical trial counts
-- phases is JSONB (e.g. ["Phase 3", "Phase 2"]) — cast to TEXT for LIKE matching
trial_counts AS (
    SELECT
        molecule_id,
        COUNT(*) AS total_trials,
        COUNT(*) FILTER (WHERE overall_status IN ('Recruiting', 'Active, not recruiting', 'Enrolling by invitation')) AS active_trials,
        COUNT(*) FILTER (WHERE phases::TEXT LIKE '%3%') AS phase_3_trials,
        COUNT(*) FILTER (WHERE phases::TEXT LIKE '%2%') AS phase_2_trials,
        COUNT(*) FILTER (WHERE phases::TEXT LIKE '%1%') AS phase_1_trials
    FROM mol_silver.clinical_trials
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Safety summary from FAERS
-- adverse_events has individual report rows with boolean seriousness flags
safety_summary AS (
    SELECT
        molecule_id,
        COUNT(*) AS total_adverse_reports,
        COUNT(*) FILTER (WHERE serious = TRUE) AS serious_adverse_reports,
        COUNT(*) FILTER (WHERE serious_death = TRUE) AS death_reports,
        MIN(receive_date) AS first_adverse_report,
        MAX(receipt_date) AS last_adverse_report
    FROM mol_silver.adverse_events
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Top adverse events (top 10 by term count)
-- meddra_pts is a JSONB array of MedDRA preferred term strings per report
top_adverse_events AS (
    SELECT
        molecule_id,
        jsonb_agg(
            jsonb_build_object(
                'term', meddra_pt,
                'count', term_count,
                'serious_count', serious_count
            ) ORDER BY term_count DESC
        ) FILTER (WHERE rn <= 10) AS top_events
    FROM (
        SELECT
            ae.molecule_id,
            meddra_pt,
            COUNT(*) AS term_count,
            COUNT(*) FILTER (WHERE ae.serious = TRUE) AS serious_count,
            ROW_NUMBER() OVER (PARTITION BY ae.molecule_id ORDER BY COUNT(*) DESC) AS rn
        FROM mol_silver.adverse_events ae
        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(ae.meddra_pts, '[]'::jsonb)) AS meddra_pt
        WHERE ae.molecule_id IS NOT NULL
        GROUP BY ae.molecule_id, meddra_pt
    ) ranked
    GROUP BY molecule_id
),

-- Drug label info (boxed warning check)
-- has_boxed_warning is already a BOOLEAN column in mol_silver.drug_labels
label_info AS (
    SELECT DISTINCT ON (molecule_id)
        molecule_id,
        has_boxed_warning,
        brand_name,
        indications_and_usage,
        effective_date
    FROM mol_silver.drug_labels
    WHERE molecule_id IS NOT NULL
    ORDER BY molecule_id, effective_date DESC
),

-- Target count (ip_silver not yet populated — returns 0 rows until ip_silver runs)
target_counts AS (
    SELECT NULL::UUID AS molecule_id, 0 AS target_count WHERE FALSE
),

-- Publication count (ip_silver not yet populated)
publication_counts AS (
    SELECT NULL::UUID AS molecule_id, 0 AS publication_count WHERE FALSE
),

-- Patent info (ip_silver not yet populated)
patent_info AS (
    SELECT
        NULL::UUID AS molecule_id,
        0 AS patent_count,
        NULL::DATE AS earliest_patent_expiry
    WHERE FALSE
),

-- Trademark info (ip_silver not yet populated)
trademark_info AS (
    SELECT
        NULL::UUID AS molecule_id,
        0 AS trademark_count,
        0 AS active_trademark_count,
        0 AS us_trademark_count,
        0 AS eu_trademark_count,
        NULL::TEXT AS latest_us_trademark_status,
        NULL::TEXT AS latest_eu_trademark_status
    WHERE FALSE
)

SELECT
    mb.molecule_id,
    mb.inchi_key,
    mb.canonical_name,
    mb.canonical_smiles,
    mb.inchi,
    mb.molecular_formula,
    mb.molecular_weight,
    mb.molecule_type,
    mb.therapeutic_areas,
    mb.mechanism_of_action,
    mb.max_phase,
    mb.resolution_confidence,

    -- Cross-references
    cr.drugbank_id,
    cr.chembl_id,
    cr.pubchem_cid,
    cr.unii,
    cr.cas_number,
    cr.rxcui,

    -- Aliases
    al.alias_list AS aliases,

    -- Trial counts
    COALESCE(tc.total_trials, 0) AS total_trials,
    COALESCE(tc.active_trials, 0) AS active_trials,
    COALESCE(tc.phase_3_trials, 0) AS phase_3_trials,
    COALESCE(tc.phase_2_trials, 0) AS phase_2_trials,
    COALESCE(tc.phase_1_trials, 0) AS phase_1_trials,

    -- Safety
    COALESCE(ss.total_adverse_reports, 0) AS total_adverse_reports,
    COALESCE(ss.serious_adverse_reports, 0) AS serious_adverse_reports,
    COALESCE(ss.death_reports, 0) AS death_reports,
    ss.first_adverse_report,
    ss.last_adverse_report,
    tae.top_events AS top_adverse_events,

    -- Label info
    COALESCE(li.has_boxed_warning, FALSE) AS has_boxed_warning,
    li.brand_name AS primary_brand_name,
    li.indications_and_usage AS primary_indication,

    -- Related entity counts (ip_silver stub — will populate when ip_silver runs)
    COALESCE(tgt.target_count, 0) AS target_count,
    COALESCE(pub.publication_count, 0) AS publication_count,
    COALESCE(pat.patent_count, 0) AS patent_count,
    pat.earliest_patent_expiry,

    -- IP Trademark section (ip_silver stub)
    COALESCE(tm.trademark_count, 0) AS trademark_count,
    COALESCE(tm.active_trademark_count, 0) AS active_trademark_count,
    COALESCE(tm.us_trademark_count, 0) AS us_trademark_count,
    COALESCE(tm.eu_trademark_count, 0) AS eu_trademark_count,
    tm.latest_us_trademark_status,
    tm.latest_eu_trademark_status,

    -- Lifecycle stage (computed from max_phase; max_phase=4 means approved in ChEMBL)
    CASE
        WHEN mb.max_phase >= 4 THEN 'Approved'
        WHEN mb.max_phase >= 3 THEN 'Phase 3'
        WHEN mb.max_phase >= 2 THEN 'Phase 2'
        WHEN mb.max_phase >= 1 THEN 'Phase 1'
        WHEN mb.max_phase = 0 THEN 'Preclinical'
        ELSE 'Unknown'
    END AS lifecycle_stage,

    -- Timestamps
    mb.created_at,
    mb.updated_at,
    NOW() AS profile_generated_at

FROM molecule_base mb
LEFT JOIN cross_refs cr ON mb.molecule_id = cr.molecule_id
LEFT JOIN aliases al ON mb.molecule_id = al.molecule_id
LEFT JOIN trial_counts tc ON mb.molecule_id = tc.molecule_id
LEFT JOIN safety_summary ss ON mb.molecule_id = ss.molecule_id
LEFT JOIN top_adverse_events tae ON mb.molecule_id = tae.molecule_id
LEFT JOIN label_info li ON mb.molecule_id = li.molecule_id
LEFT JOIN target_counts tgt ON mb.molecule_id = tgt.molecule_id
LEFT JOIN publication_counts pub ON mb.molecule_id = pub.molecule_id
LEFT JOIN patent_info pat ON mb.molecule_id = pat.molecule_id
LEFT JOIN trademark_info tm ON mb.molecule_id = tm.molecule_id;

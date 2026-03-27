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
        m.therapeutic_areas,
        m.mechanism_of_action,
        m.development_status,
        m.max_phase,
        m.first_approval_year,
        NULL::DATE                              AS approval_date,
        m.resolution_confidence,
        NULL::TEXT[]                            AS data_sources,
        m.name_source                           AS primary_source,
        m.created_at,
        m.updated_at
    FROM mol_silver.molecules m
    WHERE m.needs_review = FALSE
),

-- Get cross-reference identifiers
cross_refs AS (
    SELECT
        molecule_id,
        MAX(CASE WHEN identifier_type = 'drugbank_id' AND is_primary THEN identifier_value END) AS drugbank_id,
        MAX(CASE WHEN identifier_type = 'chembl_id' AND is_primary THEN identifier_value END) AS molecule_chembl_id,
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
trial_counts AS (
    SELECT
        molecule_id,
        COUNT(*) AS total_trials,
        COUNT(*) FILTER (WHERE overall_status IN ('Recruiting', 'Active, not recruiting', 'Enrolling by invitation')) AS active_trials,
        COUNT(*) FILTER (WHERE phase LIKE '%3%') AS phase_3_trials,
        COUNT(*) FILTER (WHERE phase LIKE '%2%') AS phase_2_trials,
        COUNT(*) FILTER (WHERE phase LIKE '%1%') AS phase_1_trials
    FROM mol_silver.clinical_trials
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Safety summary from FAERS
safety_summary AS (
    SELECT
        molecule_id,
        COALESCE(SUM(report_count), 0) AS total_adverse_reports,
        COALESCE(SUM(serious_count), 0) AS serious_adverse_reports,
        COALESCE(SUM(death_count), 0) AS death_reports,
        MIN(first_report_date) AS first_adverse_report,
        MAX(last_report_date) AS last_adverse_report
    FROM mol_silver.adverse_events
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Top adverse events (top 10 by count)
top_adverse_events AS (
    SELECT
        molecule_id,
        jsonb_agg(
            jsonb_build_object(
                'term', meddra_pt,
                'count', report_count,
                'serious_count', serious_count,
                'reporting_rate', reporting_rate
            ) ORDER BY report_count DESC
        ) FILTER (WHERE rn <= 10) AS top_events
    FROM (
        SELECT
            molecule_id,
            meddra_pt,
            report_count,
            serious_count,
            reporting_rate,
            ROW_NUMBER() OVER (PARTITION BY molecule_id ORDER BY report_count DESC) AS rn
        FROM mol_silver.adverse_events
    ) ranked
    GROUP BY molecule_id
),

-- Drug label info (boxed warning check)
label_info AS (
    SELECT DISTINCT ON (molecule_id)
        molecule_id,
        boxed_warning IS NOT NULL AND boxed_warning != '' AS has_boxed_warning,
        brand_name,
        indications_and_usage,
        effective_date
    FROM mol_silver.drug_labels
    WHERE molecule_id IS NOT NULL
    ORDER BY molecule_id, effective_date DESC
),

-- Target count
target_counts AS (
    SELECT
        molecule_id,
        COUNT(DISTINCT target_id) AS target_count
    FROM mol_silver.molecule_targets
    GROUP BY molecule_id
),

-- Publication count
publication_counts AS (
    SELECT
        molecule_id,
        COUNT(*) AS publication_count
    FROM mol_silver.molecule_publications
    GROUP BY molecule_id
),

-- Patent info
patent_info AS (
    SELECT
        molecule_id,
        COUNT(*) AS patent_count,
        MIN(expiry_date) FILTER (WHERE expiry_date > CURRENT_DATE) AS earliest_patent_expiry
    FROM mol_silver.patents
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Trademark info (IP trademark section)
-- Links trademarks to molecules via molecule_aliases (brand/trade/product names)
-- Rationale: Trademarks are registered as brand names, not generic names.
-- mol_silver.molecule_aliases already aggregates brand names from DrugBank, FDA labels,
-- Orange Book trade names, etc. — these are exactly what mark_name matches against.
trademark_info AS (
    SELECT
        ma.molecule_id,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) AS trademark_count,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) FILTER (
            WHERE t.status IN ('Registered', 'REGISTERED')
        ) AS active_trademark_count,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) FILTER (
            WHERE t.source = 'uspto_trademarks'
        ) AS us_trademark_count,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) FILTER (
            WHERE t.source = 'euipo_trademarks'
        ) AS eu_trademark_count,
        (
            SELECT t2.status
            FROM mol_silver.trademarks t2
            JOIN mol_silver.molecule_aliases ma2
                ON LOWER(t2.mark_name) = LOWER(ma2.alias_name)
            WHERE ma2.molecule_id = ma.molecule_id
              AND t2.source = 'uspto_trademarks'
              AND ma2.alias_type IN ('brand', 'trade', 'product')
            ORDER BY t2.filing_date DESC NULLS LAST
            LIMIT 1
        ) AS latest_us_trademark_status,
        (
            SELECT t3.status
            FROM mol_silver.trademarks t3
            JOIN mol_silver.molecule_aliases ma3
                ON LOWER(t3.mark_name) = LOWER(ma3.alias_name)
            WHERE ma3.molecule_id = ma.molecule_id
              AND t3.source = 'euipo_trademarks'
              AND ma3.alias_type IN ('brand', 'trade', 'product')
            ORDER BY t3.filing_date DESC NULLS LAST
            LIMIT 1
        ) AS latest_eu_trademark_status
    FROM mol_silver.molecule_aliases ma
    JOIN mol_silver.trademarks t
        ON LOWER(t.mark_name) = LOWER(ma.alias_name)
    WHERE ma.alias_type IN ('brand', 'trade', 'product')
    GROUP BY ma.molecule_id
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
    mb.development_status,
    mb.max_phase,
    mb.first_approval_year,
    mb.approval_date,
    mb.resolution_confidence,
    mb.data_sources,
    mb.primary_source,

    -- Cross-references
    cr.drugbank_id,
    cr.molecule_chembl_id,
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

    -- Related entity counts
    COALESCE(tgt.target_count, 0) AS target_count,
    COALESCE(pub.publication_count, 0) AS publication_count,
    COALESCE(pat.patent_count, 0) AS patent_count,
    pat.earliest_patent_expiry,

    -- IP Trademark section
    COALESCE(tm.trademark_count, 0) AS trademark_count,
    COALESCE(tm.active_trademark_count, 0) AS active_trademark_count,
    COALESCE(tm.us_trademark_count, 0) AS us_trademark_count,
    COALESCE(tm.eu_trademark_count, 0) AS eu_trademark_count,
    tm.latest_us_trademark_status,
    tm.latest_eu_trademark_status,

    -- Lifecycle stage (computed)
    CASE
        WHEN mb.development_status = 'approved' THEN 'Approved'
        WHEN mb.development_status = 'withdrawn' THEN 'Withdrawn'
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

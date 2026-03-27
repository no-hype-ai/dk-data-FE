-- SQLMesh Model: Gold Safety Signals
-- Aggregated safety data from FAERS and drug labels
-- Part of: 012-dk-data-platform

MODEL (
    name gold.safety_signals,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key molecule_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (molecule_id, canonical_name))
    ),
    grain molecule_id
);

WITH molecule_base AS (
    SELECT
        m.molecule_id,
        m.inchi_key,
        m.canonical_name
    FROM silver.molecules m
    WHERE m.needs_review = FALSE
),

-- Aggregate FAERS counts
faers_summary AS (
    SELECT
        molecule_id,
        COALESCE(SUM(report_count), 0) AS total_reports,
        COALESCE(SUM(serious_count), 0) AS serious_reports,
        COALESCE(SUM(death_count), 0) AS death_reports,
        COALESCE(SUM(hospitalization_count), 0) AS hospitalization_reports,
        MIN(first_report_date) AS first_report_date,
        MAX(last_report_date) AS last_report_date
    FROM silver.adverse_events
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Top adverse events with PRR/ROR
top_adverse_events AS (
    SELECT
        molecule_id,
        jsonb_agg(
            jsonb_build_object(
                'term', meddra_pt,
                'soc', meddra_soc,
                'count', report_count,
                'serious_count', serious_count,
                'death_count', death_count,
                'reporting_rate', reporting_rate,
                'prr', prr,
                'ror', ror
            ) ORDER BY report_count DESC
        ) FILTER (WHERE rn <= 20) AS top_events
    FROM (
        SELECT
            molecule_id,
            meddra_pt,
            meddra_soc,
            report_count,
            serious_count,
            death_count,
            reporting_rate,
            prr,
            ror,
            ROW_NUMBER() OVER (PARTITION BY molecule_id ORDER BY report_count DESC) AS rn
        FROM silver.adverse_events
    ) ranked
    GROUP BY molecule_id
),

-- Adverse events by System Organ Class
soc_breakdown AS (
    SELECT
        molecule_id,
        jsonb_object_agg(
            COALESCE(meddra_soc, 'Unknown'),
            jsonb_build_object(
                'count', soc_count,
                'serious_count', soc_serious
            )
        ) AS soc_distribution
    FROM (
        SELECT
            molecule_id,
            meddra_soc,
            SUM(report_count) AS soc_count,
            SUM(serious_count) AS soc_serious
        FROM silver.adverse_events
        GROUP BY molecule_id, meddra_soc
    ) soc_agg
    GROUP BY molecule_id
),

-- Get boxed warning from latest label
boxed_warnings AS (
    SELECT DISTINCT ON (molecule_id)
        molecule_id,
        boxed_warning,
        effective_date AS warning_effective_date
    FROM silver.drug_labels
    WHERE molecule_id IS NOT NULL
      AND boxed_warning IS NOT NULL
      AND boxed_warning != ''
    ORDER BY molecule_id, effective_date DESC
)

SELECT
    mb.molecule_id,
    mb.inchi_key,
    mb.canonical_name,

    -- FAERS Summary
    COALESCE(fs.total_reports, 0) AS total_reports,
    COALESCE(fs.serious_reports, 0) AS serious_reports,
    COALESCE(fs.death_reports, 0) AS death_reports,
    COALESCE(fs.hospitalization_reports, 0) AS hospitalization_reports,

    -- Percentages
    CASE
        WHEN fs.total_reports > 0
        THEN ROUND(100.0 * fs.serious_reports / fs.total_reports, 2)
        ELSE 0
    END AS serious_pct,
    CASE
        WHEN fs.total_reports > 0
        THEN ROUND(100.0 * fs.death_reports / fs.total_reports, 2)
        ELSE 0
    END AS death_pct,

    -- Date range
    fs.first_report_date,
    fs.last_report_date,

    -- Top adverse events (with signal metrics)
    tae.top_events AS top_adverse_events,

    -- SOC breakdown
    sb.soc_distribution,

    -- Boxed warning
    bw.boxed_warning,
    bw.warning_effective_date,
    bw.boxed_warning IS NOT NULL AS has_boxed_warning,

    -- Risk score (simple heuristic)
    CASE
        WHEN bw.boxed_warning IS NOT NULL THEN 'High'
        WHEN fs.death_reports > 10 THEN 'High'
        WHEN fs.serious_reports > 100 THEN 'Medium'
        WHEN fs.total_reports > 1000 THEN 'Medium'
        ELSE 'Low'
    END AS risk_level,

    NOW() AS generated_at

FROM molecule_base mb
LEFT JOIN faers_summary fs ON mb.molecule_id = fs.molecule_id
LEFT JOIN top_adverse_events tae ON mb.molecule_id = tae.molecule_id
LEFT JOIN soc_breakdown sb ON mb.molecule_id = sb.molecule_id
LEFT JOIN boxed_warnings bw ON mb.molecule_id = bw.molecule_id
WHERE fs.total_reports > 0 OR bw.boxed_warning IS NOT NULL;  -- Only include molecules with safety data

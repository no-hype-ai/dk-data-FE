-- SQLMesh Model: Gold Safety Signals
-- Aggregated safety data from report-level Silver adverse_events + drug labels
-- Silver is now report-level (zero data loss); aggregation happens HERE in Gold.

MODEL (
    name mol_gold.safety_signals,
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
        m.id AS molecule_id,
        m.inchi_key,
        m.canonical_name
    FROM mol_silver.molecules m
    WHERE m.needs_review = FALSE
),

-- Expand report-level MedDRA PTs and aggregate by molecule
expanded_reports AS (
    SELECT
        ae.molecule_id,
        meddra_pt,
        ae.serious,
        ae.serious_death,
        ae.serious_hospitalization,
        ae.receive_date
    FROM mol_silver.adverse_events ae,
         jsonb_array_elements_text(ae.meddra_pts) AS meddra_pt
    WHERE ae.molecule_id IS NOT NULL
      AND ae.meddra_pts IS NOT NULL
),

-- Aggregate FAERS counts per molecule
faers_summary AS (
    SELECT
        molecule_id,
        COUNT(*) AS total_reports,
        SUM(CASE WHEN serious THEN 1 ELSE 0 END) AS serious_reports,
        SUM(CASE WHEN serious_death THEN 1 ELSE 0 END) AS death_reports,
        SUM(CASE WHEN serious_hospitalization THEN 1 ELSE 0 END) AS hospitalization_reports,
        MIN(receive_date) AS first_report_date,
        MAX(receive_date) AS last_report_date
    FROM mol_silver.adverse_events
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Aggregate by molecule + MedDRA PT for top events
pt_counts AS (
    SELECT
        molecule_id,
        meddra_pt,
        COUNT(*) AS report_count,
        SUM(CASE WHEN serious THEN 1 ELSE 0 END) AS serious_count,
        SUM(CASE WHEN serious_death THEN 1 ELSE 0 END) AS death_count
    FROM expanded_reports
    GROUP BY molecule_id, meddra_pt
),

-- Top 20 adverse events per molecule
top_adverse_events AS (
    SELECT
        molecule_id,
        jsonb_agg(
            jsonb_build_object(
                'term', meddra_pt,
                'count', report_count,
                'serious_count', serious_count,
                'death_count', death_count
            ) ORDER BY report_count DESC
        ) FILTER (WHERE rn <= 20) AS top_events
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (PARTITION BY molecule_id ORDER BY report_count DESC) AS rn
        FROM pt_counts
    ) ranked
    GROUP BY molecule_id
),

-- Get boxed warning from latest label
boxed_warnings AS (
    SELECT DISTINCT ON (molecule_id)
        molecule_id,
        boxed_warning,
        effective_date AS warning_effective_date
    FROM mol_silver.drug_labels
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

    -- Top adverse events
    tae.top_events AS top_adverse_events,

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
LEFT JOIN boxed_warnings bw ON mb.molecule_id = bw.molecule_id
WHERE fs.total_reports > 0 OR bw.boxed_warning IS NOT NULL;

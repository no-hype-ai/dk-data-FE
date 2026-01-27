-- SQLMesh Model: Silver Adverse Events
-- Aggregated FAERS data by molecule and MedDRA preferred term
-- Part of: 012-dk-data-platform

MODEL (
    name silver.adverse_events,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, meddra_pt),
        when_matched_update_all TRUE
    ),
    cron '@weekly',
    audits (
        not_null(columns := (molecule_id, meddra_pt))
    ),
    grain (molecule_id, meddra_pt)
);

-- Aggregate FAERS events by molecule and adverse event term
WITH linked_events AS (
    -- Link FAERS drug names to Silver molecules using fuzzy matching
    SELECT
        m.id AS molecule_id,
        m.inchi_key,
        m.canonical_name,
        f.meddra_pts,
        f.serious,
        f.serious_death,
        f.serious_hospitalization,
        f.receive_date
    FROM bronze.faers_events f
    JOIN silver.molecules m ON (
        -- Exact match on canonical name
        LOWER(f.drug_name) = LOWER(m.canonical_name)
        -- Or fuzzy match with high similarity
        OR similarity(LOWER(f.drug_name), LOWER(m.canonical_name)) > 0.8
    )
    WHERE
        f.processed_to_silver = FALSE
        AND m.needs_review = FALSE
        AND f.meddra_pts IS NOT NULL
),

expanded_reactions AS (
    -- Expand MedDRA PT array into rows
    SELECT
        molecule_id,
        inchi_key,
        canonical_name,
        meddra_pt,
        serious,
        serious_death,
        serious_hospitalization,
        receive_date
    FROM linked_events,
         jsonb_array_elements_text(meddra_pts) AS meddra_pt
),

aggregated AS (
    -- Aggregate by molecule and PT
    SELECT
        gen_random_uuid() AS id,
        molecule_id,
        meddra_pt,
        NULL::VARCHAR(20) AS meddra_pt_code,  -- Would need MedDRA lookup
        NULL::VARCHAR(200) AS meddra_soc,     -- Would need MedDRA hierarchy
        NULL::VARCHAR(20) AS meddra_soc_code,
        COUNT(*) AS report_count,
        SUM(CASE WHEN serious THEN 1 ELSE 0 END) AS serious_count,
        SUM(CASE WHEN serious_death THEN 1 ELSE 0 END) AS death_count,
        SUM(CASE WHEN serious_hospitalization THEN 1 ELSE 0 END) AS hospitalization_count,
        NULL::NUMERIC(10,4) AS reporting_rate,  -- Calculated in Gold layer
        NULL::NUMERIC(10,4) AS prr,             -- Calculated in Gold layer
        NULL::NUMERIC(10,4) AS ror,             -- Calculated in Gold layer
        MIN(receive_date) AS first_report_date,
        MAX(receive_date) AS last_report_date,
        'openfda_faers' AS source,
        NOW() AS created_at,
        NOW() AS updated_at
    FROM expanded_reactions
    GROUP BY molecule_id, meddra_pt
)

SELECT * FROM aggregated;


-- Post-insert: Mark Bronze FAERS records as processed for linked drugs
@post_incremental(
    UPDATE bronze.faers_events f
    SET processed_to_silver = TRUE
    WHERE processed_to_silver = FALSE
    AND EXISTS (
        SELECT 1 FROM silver.molecules m
        WHERE LOWER(f.drug_name) = LOWER(m.canonical_name)
           OR similarity(LOWER(f.drug_name), LOWER(m.canonical_name)) > 0.8
    )
);

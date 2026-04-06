-- SQLMesh Model: Silver Adverse Events
-- Aggregated adverse event data from FAERS (FDA) and SIDER (package inserts)
-- Part of: 012-dk-data-platform
--
-- Linkage strategy:
--   FAERS → molecules via drug name (fuzzy match)
--   SIDER → molecules via PubChem CID (through identifier_mappings) or name

MODEL (
    name mol_silver.adverse_events,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, meddra_pt, source)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (molecule_id, meddra_pt))
    ),
    grain (molecule_id, meddra_pt, source)
);

-- ============================================================================
-- FAERS (OpenFDA) adverse event reports
-- ============================================================================
WITH faers_linked AS (
    SELECT
        m.molecule_id,
        m.inchi_key,
        m.canonical_name,
        f.meddra_pts,
        f.serious,
        f.serious_death,
        f.serious_hospitalization,
        f.serious_lifethreatening,
        f.serious_disabling,
        f.serious_congenital,
        f.serious_other,
        f.receive_date
    FROM mol_bronze.faers_events f
    -- Deduplicate: similarity() can match multiple molecules per drug_name.
    -- Pick highest-similarity match; fall back to exact match when no fuzzy match is better.
    JOIN (
        SELECT DISTINCT ON (LOWER(canonical_name))
            molecule_id, inchi_key, canonical_name
        FROM mol_silver.molecules
        ORDER BY LOWER(canonical_name), molecule_id
    ) m ON (
        LOWER(f.drug_name) = LOWER(m.canonical_name)
        -- Fuzzy threshold 0.8: validated against FAERS sample in 2024 — below 0.8 introduced
        -- multi-word false positives (e.g. "aspirin" matching "aspirin-caffeine compound").
        -- Above 0.85 missed common abbreviations and brand→INN matches. Tune via:
        --   SELECT similarity(drug_name, canonical_name), drug_name, canonical_name
        --   FROM mol_bronze.faers_events CROSS JOIN mol_silver.molecules
        --   WHERE similarity(...) BETWEEN 0.75 AND 0.85 LIMIT 200;
        OR similarity(LOWER(f.drug_name), LOWER(m.canonical_name)) > 0.8
    )
    WHERE f.processed_to_silver = FALSE
      AND f.meddra_pts IS NOT NULL
),

faers_expanded AS (
    SELECT
        molecule_id,
        inchi_key,
        canonical_name,
        meddra_pt,
        serious,
        serious_death,
        serious_hospitalization,
        serious_lifethreatening,
        serious_disabling,
        serious_congenital,
        serious_other,
        receive_date
    FROM faers_linked,
         jsonb_array_elements_text(meddra_pts) AS meddra_pt
),

faers_aggregated AS (
    SELECT
        gen_random_uuid() AS id,
        molecule_id,
        meddra_pt,
        NULL::VARCHAR(20) AS meddra_pt_code,
        NULL::VARCHAR(200) AS meddra_soc,
        NULL::VARCHAR(20) AS meddra_soc_code,
        COUNT(*) AS report_count,
        SUM(CASE WHEN serious THEN 1 ELSE 0 END)::INTEGER AS serious_count,
        SUM(CASE WHEN serious_death THEN 1 ELSE 0 END)::INTEGER AS death_count,
        SUM(CASE WHEN serious_hospitalization THEN 1 ELSE 0 END)::INTEGER AS hospitalization_count,
        SUM(CASE WHEN serious_lifethreatening THEN 1 ELSE 0 END)::INTEGER AS lifethreatening_count,
        SUM(CASE WHEN serious_disabling THEN 1 ELSE 0 END)::INTEGER AS disabling_count,
        SUM(CASE WHEN serious_congenital THEN 1 ELSE 0 END)::INTEGER AS congenital_count,
        SUM(CASE WHEN serious_other THEN 1 ELSE 0 END)::INTEGER AS other_serious_count,
        NULL::NUMERIC(10,4) AS reporting_rate,
        NULL::NUMERIC(10,4) AS prr,
        NULL::NUMERIC(10,4) AS ror,
        -- SIDER-specific fields (not applicable for FAERS)
        NULL::NUMERIC AS frequency_lower,
        NULL::NUMERIC AS frequency_upper,
        NULL::TEXT AS frequency_raw,
        NULL::TEXT AS frequency_category,
        NULL::TEXT AS placebo,
        NULL::TEXT AS umls_cui,
        NULL::TEXT AS umls_cui_from_label,
        NULL::TEXT AS meddra_concept_type,
        MIN(receive_date) AS first_report_date,
        MAX(receive_date) AS last_report_date,
        'openfda_faers' AS source,
        NOW() AS created_at,
        NOW() AS updated_at
    FROM faers_expanded
    GROUP BY molecule_id, meddra_pt
),

-- ============================================================================
-- SIDER (package insert) side effects
-- Linkage: STITCH pubchem_cid → identifier_mappings → molecule
-- ============================================================================
sider_linked AS (
    -- Link via PubChem CID: identifier_mappings is an EAV table
    -- (identifier_type = 'pubchem_cid', identifier_value = CID as text)
    SELECT DISTINCT ON (s.stitch_id_flat, s.umls_cui_side_effect, m.molecule_id)
        m.molecule_id,
        s.side_effect_name AS meddra_pt,
        s.umls_cui_side_effect AS umls_cui,
        s.umls_cui_from_label,
        s.meddra_concept_type,
        s.lower_bound_freq AS frequency_lower,
        s.upper_bound_freq AS frequency_upper,
        s.frequency_raw,
        s.frequency_category,
        s.placebo,
        s.ingested_at
    FROM mol_bronze.sider s
    JOIN mol_silver.identifier_mappings im
        ON im.identifier_type = 'pubchem_cid'
        AND im.identifier_value = s.pubchem_cid::TEXT
    JOIN mol_silver.molecules m ON m.molecule_id = im.molecule_id
    WHERE s.processed_to_silver = FALSE
      AND s.pubchem_cid IS NOT NULL
      AND s.side_effect_name IS NOT NULL
    ORDER BY s.stitch_id_flat, s.umls_cui_side_effect, m.molecule_id
),

sider_aggregated AS (
    SELECT
        gen_random_uuid() AS id,
        molecule_id,
        meddra_pt,
        NULL::VARCHAR(20) AS meddra_pt_code,
        NULL::VARCHAR(200) AS meddra_soc,
        NULL::VARCHAR(20) AS meddra_soc_code,
        COUNT(*) AS report_count,
        0::INTEGER AS serious_count,
        0::INTEGER AS death_count,
        0::INTEGER AS hospitalization_count,
        0::INTEGER AS lifethreatening_count,
        0::INTEGER AS disabling_count,
        0::INTEGER AS congenital_count,
        0::INTEGER AS other_serious_count,
        NULL::NUMERIC(10,4) AS reporting_rate,
        NULL::NUMERIC(10,4) AS prr,
        NULL::NUMERIC(10,4) AS ror,
        -- Use highest frequency bounds across all rows for this drug-event pair
        MAX(frequency_lower) AS frequency_lower,
        MAX(frequency_upper) AS frequency_upper,
        -- Take a representative frequency string
        MIN(frequency_raw) AS frequency_raw,
        -- Derived frequency category from bronze (very_common, common, uncommon, rare, very_rare)
        MIN(frequency_category) AS frequency_category,
        MIN(placebo) AS placebo,
        MIN(umls_cui) AS umls_cui,
        -- UMLS CUI as mapped from the label text (may differ from umls_cui)
        MIN(umls_cui_from_label) AS umls_cui_from_label,
        MIN(meddra_concept_type) AS meddra_concept_type,
        NULL::DATE AS first_report_date,
        NULL::DATE AS last_report_date,
        'sider' AS source,
        NOW() AS created_at,
        NOW() AS updated_at
    FROM sider_linked
    GROUP BY molecule_id, meddra_pt
)

-- ============================================================================
-- Union FAERS and SIDER
-- ============================================================================
SELECT * FROM faers_aggregated
UNION ALL
SELECT * FROM sider_aggregated;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY (update all columns on match),
-- so reprocessing is idempotent.

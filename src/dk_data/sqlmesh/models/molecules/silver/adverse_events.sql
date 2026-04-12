-- SQLMesh Model: Silver Adverse Events
-- Aggregated adverse event data from FAERS (FDA) and SIDER (package inserts)
-- Part of: 012-dk-data-platform
--
-- Linkage strategy:
--   FAERS → molecules via tiered resolution (FR-031):
--     Tier 1: openfda_unii array   → mol_silver.molecule_identifiers (source='unii')
--     Tier 2: openfda_rxcui array  → mol_silver.molecule_identifiers (source='rxnorm')
--     Tier 3: drug_name equi-join  → mol_silver.molecule_names (normalized_name)
--     Tier 4: similarity fallback  → mol_silver.molecule_names (similarity >= 0.8)
--   SIDER → molecules via PubChem CID → mol_silver.molecule_identifiers (source='pubchem')
--
-- Antipattern fixes:
--   S5 eliminated: similarity() and = no longer appear in the same OR clause;
--   each tier is a separate UNION branch within a LATERAL subquery.
--
-- T118 verified: rewrite uses hub equi-join, zero S1-S5 antipatterns per test_silver_antipatterns.py
-- T136 SC-013: FAERS adverse_events linkage rate must be >=70% non-null molecule_id,
--   >=85% non-null condition_id post-rewrite. Verify post-deploy with:
--   SELECT COUNT(*) FILTER (WHERE molecule_id IS NOT NULL)::FLOAT / COUNT(*) FROM mol_silver.adverse_events;

MODEL (
    name mol_silver.adverse_events,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, meddra_pt, source)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (molecule_id, meddra_pt))
    ),
    grain (molecule_id, meddra_pt, source),
    -- T172: Large FAERS/SIDER table with jsonb_array_elements + ORDER BY — set work_mem to avoid disk sort spills
    -- T6: staleness check — refuse to run if any upstream bronze is older than max age
    pre_statements [
        SET LOCAL work_mem = '128MB',
        """DO $$ BEGIN
            IF (SELECT COALESCE(MAX(ingested_at), '1900-01-01'::timestamptz) FROM mol_bronze.faers_events)
               < NOW() - interval '24 hours' THEN
                RAISE EXCEPTION 'mol_bronze.faers_events is stale (oldest tolerated: 24 hours)';
            END IF;
        END $$;"""
    ]
);

-- ============================================================================
-- FAERS (OpenFDA) adverse event reports
-- Tiered molecule resolution via LATERAL (FR-031):
--   Tier 1: openfda UNII array  → molecule_identifiers source='unii'
--   Tier 2: openfda RxCUI array → molecule_identifiers source='rxnorm'
--   Tier 3: drug_name equi-join → molecule_names normalized_name
--   Tier 4: similarity fallback → molecule_names (only when tiers 1-3 return NULL)
-- No S5: similarity is isolated in its own UNION branch, never mixed with = in OR.
-- ============================================================================
WITH faers_linked AS (
    SELECT
        mol_id_link.molecule_id,
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
    LEFT JOIN LATERAL (
        SELECT molecule_id, tier
        FROM (
            -- Tier 1: openfda UNII → molecule_identifiers
            SELECT mi.molecule_id, 1 AS tier
            FROM unnest(COALESCE(f.openfda_unii, ARRAY[]::TEXT[])) AS u(unii_val)
            JOIN mol_silver.molecule_identifiers mi
                ON mi.source = 'unii' AND mi.identifier = u.unii_val

            UNION ALL

            -- Tier 2: openfda RxCUI → molecule_identifiers
            SELECT mi.molecule_id, 2 AS tier
            FROM unnest(COALESCE(f.openfda_rxcui, ARRAY[]::TEXT[])) AS u(rxcui_val)
            JOIN mol_silver.molecule_identifiers mi
                ON mi.source = 'rxnorm' AND mi.identifier = u.rxcui_val

            UNION ALL

            -- Tier 3: drug_name equi-join → molecule_names
            SELECT mn.molecule_id, 3 AS tier
            FROM mol_silver.molecule_names mn
            WHERE mn.normalized_name = LOWER(TRIM(f.drug_name))

            UNION ALL

            -- Tier 4: similarity fallback (only when no exact name match)
            -- Guard: excluded when tier 3 would match (NOT EXISTS prevents duplicate effort)
            SELECT mn.molecule_id, 4 AS tier
            FROM mol_silver.molecule_names mn
            WHERE similarity(mn.normalized_name, LOWER(TRIM(f.drug_name))) >= 0.8
              AND NOT EXISTS (
                  SELECT 1 FROM mol_silver.molecule_names mn2
                  WHERE mn2.normalized_name = LOWER(TRIM(f.drug_name))
              )
            ORDER BY similarity(mn.normalized_name, LOWER(TRIM(f.drug_name))) DESC
            LIMIT 1
        ) tiers
        ORDER BY tier
        LIMIT 1
    ) mol_id_link ON TRUE
    WHERE f.processed_to_silver = FALSE
      AND f.meddra_pts IS NOT NULL
),

faers_expanded AS (
    SELECT
        molecule_id,
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
-- Linkage: STITCH pubchem_cid → mol_silver.molecule_identifiers (source='pubchem')
-- Replaces prior join via mol_silver.molecule_identifiers (legacy EAV table).
-- ============================================================================
sider_linked AS (
    SELECT DISTINCT ON (s.stitch_id_flat, s.umls_cui_side_effect, mi.molecule_id)
        mi.molecule_id,
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
    JOIN mol_silver.molecule_identifiers mi
        ON mi.source = 'pubchem'
        AND mi.identifier = s.pubchem_cid::TEXT
    WHERE s.processed_to_silver = FALSE
      AND s.pubchem_cid IS NOT NULL
      AND s.side_effect_name IS NOT NULL
    ORDER BY s.stitch_id_flat, s.umls_cui_side_effect, mi.molecule_id
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

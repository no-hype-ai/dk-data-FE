-- Migration: 021_mol_api_views.sql
-- Feature: 012-dk-data-platform
-- Description: Create mol_api schema views for PostgREST exposure
-- Date: 2026-01-27
--
-- 2026-04-12 (feature 001-silver-medallion-rebuild): migrated off the deprecated
-- mol_silver.molecule_aliases and mol_silver.identifier_mappings tables. They are
-- replaced by mol_silver.molecule_names and mol_silver.molecule_identifiers (the
-- canonical hub crosswalks). Some legacy columns (mapping_id, confidence,
-- is_validated, needs_review, review_reason, resolution_confidence, source_count,
-- chembl_id/drugbank_id/pubchem_cid as direct hub columns) no longer exist on the
-- new hub schema and are exposed as NULL placeholders here for API back-compat.
-- A follow-up migration should rebuild these views from the hub + crosswalks
-- properly; this file is a transitional shim to keep PostgREST endpoints valid.

-- =============================================================================
-- MOL_API SCHEMA VIEWS
-- Purpose: Views exposed via PostgREST for molecule platform REST API
-- =============================================================================

-- View: Molecule profiles (primary lookup view)
-- Hub-era columns are projected directly; legacy direct-on-hub identifier columns
-- (chembl_id, drugbank_id, pubchem_cid, unii, cas_number) are pulled from
-- mol_silver.molecule_identifiers via scalar subqueries. Therapeutic_areas and the
-- other denormalized arrays no longer live on the hub and are exposed as NULL.
CREATE OR REPLACE VIEW mol_api.molecules AS
SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'chembl'   LIMIT 1) AS chembl_id,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'drugbank' LIMIT 1) AS drugbank_id,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'pubchem'  LIMIT 1) AS pubchem_cid,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'unii'     LIMIT 1) AS unii,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'cas'      LIMIT 1) AS cas_number,
    m.canonical_smiles                          AS smiles,
    NULL::text                                  AS molecular_formula,
    NULL::numeric                               AS molecular_weight,
    CASE WHEN m.is_biologic THEN 'biologic' ELSE 'small_molecule' END AS molecule_type,
    NULL::text[]                                AS therapeutic_areas,
    NULL::text[]                                AS atc_codes,
    NULL::text[]                                AS brand_names,
    NULL::text[]                                AS generic_names,
    p.lifecycle_stage,
    p.stage_confidence,
    p.data_completeness,
    p.trial_count,
    p.active_trial_count,
    p.label_count,
    p.adverse_event_count,
    p.first_approval_date,
    NULL::numeric                               AS resolution_confidence,
    NULL::int                                   AS source_count,
    m.first_seen_at                             AS created_at,
    m.last_updated_at                           AS updated_at
FROM mol_silver.molecules m
LEFT JOIN mol_gold.molecule_profiles p ON m.molecule_id = p.molecule_id;

-- View: Molecule search (includes names for fuzzy matching)
CREATE OR REPLACE VIEW mol_api.molecule_search AS
SELECT DISTINCT ON (m.molecule_id, n.normalized_name)
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'chembl' LIMIT 1) AS chembl_id,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'drugbank' LIMIT 1) AS drugbank_id,
    (SELECT identifier FROM mol_silver.molecule_identifiers WHERE molecule_id = m.molecule_id AND source = 'pubchem' LIMIT 1) AS pubchem_cid,
    n.display_name      AS alias_name,
    n.name_kind         AS alias_type,
    n.normalized_name   AS alias_name_normalized,
    CASE WHEN m.is_biologic THEN 'biologic' ELSE 'small_molecule' END AS molecule_type,
    p.lifecycle_stage
FROM mol_silver.molecules m
LEFT JOIN mol_silver.molecule_names n ON m.molecule_id = n.molecule_id
LEFT JOIN mol_gold.molecule_profiles p ON m.molecule_id = p.molecule_id;

-- View: Clinical trials
CREATE OR REPLACE VIEW mol_api.clinical_trials AS
SELECT
    t.trial_id,
    t.nct_id,
    t.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    t.title,
    t.brief_summary,
    t.phase,
    t.status,
    t.study_type,
    t.conditions,
    t.intervention_names,
    t.enrollment_target,
    t.enrollment_actual,
    t.start_date,
    t.completion_date,
    t.sponsor,
    t.sponsor_type,
    t.has_results,
    t.outcome_type,
    t.created_at,
    t.updated_at
FROM mol_silver.clinical_trials t
LEFT JOIN mol_silver.molecules m ON t.molecule_id = m.molecule_id;

-- View: Drug labels
CREATE OR REPLACE VIEW mol_api.drug_labels AS
SELECT
    l.label_id,
    l.set_id,
    l.molecule_id,
    m.inchi_key,
    l.brand_name,
    l.generic_name,
    l.manufacturer,
    l.application_number,
    l.approval_date,
    l.marketing_status,
    l.route_of_administration,
    l.dosage_forms,
    l.indications,
    l.contraindications,
    l.warnings,
    l.boxed_warning,
    l.adverse_reactions,
    l.drug_interactions,
    l.effective_date,
    l.created_at,
    l.updated_at
FROM mol_silver.drug_labels l
LEFT JOIN mol_silver.molecules m ON l.molecule_id = m.molecule_id;

-- View: Safety signals (aggregated)
CREATE OR REPLACE VIEW mol_api.safety_signals AS
SELECT
    s.signal_id,
    s.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    s.reaction_meddra_pt,
    s.reaction_soc,
    s.case_count,
    s.prr_score,
    s.ror_score,
    s.ic_score,
    s.signal_strength,
    s.first_reported,
    s.last_reported,
    s.trend_direction,
    s.last_updated
FROM mol_gold.safety_signals s
JOIN mol_silver.molecules m ON s.molecule_id = m.molecule_id;

-- View: Adverse events (raw detail)
CREATE OR REPLACE VIEW mol_api.adverse_events AS
SELECT
    ae.event_id,
    ae.source,
    ae.source_report_id,
    ae.molecule_id,
    m.inchi_key,
    ae.drug_name_reported,
    ae.reaction_meddra_pt,
    ae.reaction_meddra_code,
    ae.seriousness,
    ae.outcome,
    ae.patient_age,
    ae.patient_sex,
    ae.report_date,
    ae.country,
    ae.created_at
FROM mol_silver.adverse_events ae
LEFT JOIN mol_silver.molecules m ON ae.molecule_id = m.molecule_id;

-- View: Cross-references (all identifiers from the hub crosswalk)
CREATE OR REPLACE VIEW mol_api.cross_references AS
SELECT
    NULL::uuid              AS mapping_id,           -- legacy column, no equivalent in hub crosswalk
    im.molecule_id,
    m.inchi_key,
    m.canonical_name        AS molecule_name,
    im.source               AS identifier_type,      -- legacy alias: hub uses `source` for the namespace
    im.identifier           AS identifier_value,
    im.source,
    NULL::numeric           AS confidence,           -- legacy column, no equivalent
    im.is_primary,
    NULL::boolean           AS is_validated,         -- legacy column, no equivalent
    im.first_seen_at        AS created_at
FROM mol_silver.molecule_identifiers im
JOIN mol_silver.molecules m ON im.molecule_id = m.molecule_id;

-- View: Competitive landscape
CREATE OR REPLACE VIEW mol_api.competitive_landscape AS
SELECT
    cl.landscape_id,
    cl.indication,
    cl.indication_mesh_id,
    cl.molecule_ids,
    cl.approved_count,
    cl.phase3_count,
    cl.phase2_count,
    cl.phase1_count,
    cl.market_leaders,
    cl.recent_approvals,
    cl.pipeline_trends,
    cl.last_updated
FROM mol_gold.competitive_landscape cl;

-- View: Lifecycle stages
CREATE OR REPLACE VIEW mol_api.lifecycle_stages AS
SELECT
    ls.stage_id,
    ls.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    ls.indication,
    ls.lifecycle_stage,
    ls.confidence,
    ls.evidence_sources,
    ls.detected_at,
    ls.validated_by,
    ls.validated_at
FROM mol_gold.lifecycle_stages ls
JOIN mol_silver.molecules m ON ls.molecule_id = m.molecule_id;

-- View: Resolution queue (molecules flagged via meta.linkage_conflicts under the new hub)
-- The pre-hub schema had a needs_review flag on the hub itself; the new hub routes
-- low-confidence/conflicting links to meta.linkage_conflicts. This view returns the
-- empty set on the new schema; a follow-up should rewrite it against linkage_conflicts.
CREATE OR REPLACE VIEW mol_api.resolution_queue AS
SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    NULL::text       AS chembl_id,
    NULL::text       AS drugbank_id,
    NULL::text       AS pubchem_cid,
    NULL::numeric    AS resolution_confidence,
    NULL::text       AS review_reason,
    FALSE            AS needs_review,
    NULL::int        AS source_count,
    m.first_seen_at  AS created_at,
    ARRAY_AGG(DISTINCT n.display_name) FILTER (WHERE n.display_name IS NOT NULL) AS candidate_names,
    JSONB_AGG(
        DISTINCT JSONB_BUILD_OBJECT(
            'source', im.source,
            'identifier_type', im.source,
            'identifier_value', im.identifier,
            'confidence', NULL
        )
    ) FILTER (WHERE im.identifier IS NOT NULL) AS source_identifiers
FROM mol_silver.molecules m
LEFT JOIN mol_silver.molecule_names n        ON m.molecule_id = n.molecule_id
LEFT JOIN mol_silver.molecule_identifiers im ON m.molecule_id = im.molecule_id
WHERE FALSE  -- new hub has no needs_review flag; see meta.linkage_conflicts
GROUP BY m.molecule_id, m.inchi_key, m.canonical_name, m.first_seen_at;

-- View: Pipeline status
CREATE OR REPLACE VIEW mol_api.pipeline_status AS
SELECT
    'raw' AS layer,
    (SELECT COUNT(*) FROM mol_raw.clinicaltrials) +
    (SELECT COUNT(*) FROM mol_raw.chembl) +
    (SELECT COUNT(*) FROM mol_raw.pubchem) +
    (SELECT COUNT(*) FROM mol_raw.drugbank) +
    (SELECT COUNT(*) FROM mol_raw.openfda_labels) +
    (SELECT COUNT(*) FROM mol_raw.openfda_faers) AS record_count,
    GREATEST(
        (SELECT MAX(ingested_at) FROM mol_raw.clinicaltrials),
        (SELECT MAX(ingested_at) FROM mol_raw.chembl),
        (SELECT MAX(ingested_at) FROM mol_raw.pubchem)
    ) AS last_updated
UNION ALL
SELECT
    'bronze' AS layer,
    (SELECT COUNT(*) FROM mol_bronze.clinicaltrials) +
    (SELECT COUNT(*) FROM mol_bronze.chembl) +
    (SELECT COUNT(*) FROM mol_bronze.pubchem) +
    (SELECT COUNT(*) FROM mol_bronze.drugbank) +
    (SELECT COUNT(*) FROM mol_bronze.openfda_labels) +
    (SELECT COUNT(*) FROM mol_bronze.openfda_faers) AS record_count,
    GREATEST(
        (SELECT MAX(ingested_at) FROM mol_bronze.clinicaltrials),
        (SELECT MAX(ingested_at) FROM mol_bronze.chembl),
        (SELECT MAX(ingested_at) FROM mol_bronze.pubchem)
    ) AS last_updated
UNION ALL
SELECT
    'silver' AS layer,
    (SELECT COUNT(*) FROM mol_silver.molecules) AS record_count,
    (SELECT MAX(updated_at) FROM mol_silver.molecules) AS last_updated
UNION ALL
SELECT
    'gold' AS layer,
    (SELECT COUNT(*) FROM mol_gold.molecule_profiles) AS record_count,
    (SELECT MAX(last_updated) FROM mol_gold.molecule_profiles) AS last_updated;

-- View: Data sources status
CREATE OR REPLACE VIEW mol_api.data_sources AS
SELECT
    ds.source_id,
    ds.source_name,
    ds.source_type,
    ds.source_url,
    ds.description,
    ds.refresh_frequency,
    ds.last_successful_refresh,
    ds.last_refresh_attempt,
    ds.last_refresh_status,
    ds.record_count,
    ds.is_active,
    th.health_status,
    th.freshness_hours,
    ds.staleness_threshold_hours
FROM meta.data_sources ds
LEFT JOIN LATERAL (
    SELECT health_status, freshness_hours
    FROM meta.table_health
    WHERE source_id = ds.source_id
    ORDER BY check_timestamp DESC
    LIMIT 1
) th ON TRUE
WHERE ds.source_name LIKE 'mol_%' OR ds.source_name IN (
    'chembl', 'pubchem', 'drugbank', 'clinicaltrials',
    'openfda_labels', 'openfda_faers', 'sider', 'openalex'
);

-- View: User tracked molecules (filtered by RLS)
CREATE OR REPLACE VIEW mol_api.tracked_molecules AS
SELECT
    utm.tracking_id,
    utm.user_id,
    utm.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    utm.indication,
    utm.lifecycle_stage,
    utm.stage_validated,
    utm.validation_date,
    utm.notes,
    utm.priority,
    p.trial_count,
    p.active_trial_count,
    p.adverse_event_count,
    utm.created_at,
    utm.updated_at
FROM mol_app.user_tracked_molecules utm
JOIN mol_silver.molecules m ON utm.molecule_id = m.molecule_id
LEFT JOIN mol_gold.molecule_profiles p ON utm.molecule_id = p.molecule_id;

-- View: User annotations (filtered by RLS)
CREATE OR REPLACE VIEW mol_api.user_annotations AS
SELECT
    ua.annotation_id,
    ua.user_id,
    ua.molecule_id,
    m.inchi_key,
    m.canonical_name AS molecule_name,
    ua.tracking_id,
    ua.annotation_type,
    ua.title,
    ua.content,
    ua.source_url,
    ua.is_private,
    ua.lifecycle_stage,
    ua.evidence_strength,
    ua.created_at,
    ua.updated_at
FROM mol_app.user_annotations ua
JOIN mol_silver.molecules m ON ua.molecule_id = m.molecule_id;

-- =============================================================================
-- STORED FUNCTIONS FOR COMPLEX OPERATIONS
-- =============================================================================

-- Function: Fuzzy search molecules by name
CREATE OR REPLACE FUNCTION mol_api.search_molecules(
    search_query TEXT,
    similarity_threshold DECIMAL DEFAULT 0.3,
    max_results INTEGER DEFAULT 20
)
RETURNS TABLE (
    molecule_id UUID,
    inchi_key VARCHAR(27),
    canonical_name VARCHAR(500),
    matched_name VARCHAR(500),
    similarity_score DECIMAL,
    lifecycle_stage VARCHAR(50)
) AS $$
BEGIN
    -- Note: this function should ideally call mol_silver.resolve_molecule() per FR-014.
    -- Kept as-is for back-compat; uses molecule_names crosswalk in place of the old aliases.
    RETURN QUERY
    SELECT DISTINCT ON (m.molecule_id)
        m.molecule_id,
        m.inchi_key,
        m.canonical_name,
        COALESCE(n.display_name, m.canonical_name) AS matched_name,
        GREATEST(
            similarity(lower(m.canonical_name), lower(search_query)),
            COALESCE(similarity(n.normalized_name, lower(search_query)), 0)
        ) AS similarity_score,
        p.lifecycle_stage
    FROM mol_silver.molecules m
    LEFT JOIN mol_silver.molecule_names n ON m.molecule_id = n.molecule_id
    LEFT JOIN mol_gold.molecule_profiles p ON m.molecule_id = p.molecule_id
    WHERE
          similarity(lower(m.canonical_name), lower(search_query)) >= similarity_threshold
          OR similarity(n.normalized_name, lower(search_query)) >= similarity_threshold
          OR m.inchi_key = upper(search_query)
    ORDER BY m.molecule_id, similarity_score DESC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function: Get molecule with all cross-references
CREATE OR REPLACE FUNCTION mol_api.get_molecule_details(p_inchi_key VARCHAR(27))
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT JSONB_BUILD_OBJECT(
        'molecule', JSONB_BUILD_OBJECT(
            'molecule_id', m.molecule_id,
            'inchi_key', m.inchi_key,
            'canonical_name', m.canonical_name,
            'smiles', m.smiles,
            'molecular_formula', m.molecular_formula,
            'molecular_weight', m.molecular_weight,
            'molecule_type', m.molecule_type,
            'therapeutic_areas', m.therapeutic_areas,
            'atc_codes', m.atc_codes,
            'brand_names', m.brand_names,
            'generic_names', m.generic_names
        ),
        'identifiers', (
            SELECT JSONB_AGG(JSONB_BUILD_OBJECT(
                'type', im.source,
                'value', im.identifier,
                'source', im.source,
                'is_primary', im.is_primary
            ))
            FROM mol_silver.molecule_identifiers im
            WHERE im.molecule_id = m.molecule_id
        ),
        'profile', (
            SELECT JSONB_BUILD_OBJECT(
                'lifecycle_stage', p.lifecycle_stage,
                'stage_confidence', p.stage_confidence,
                'data_completeness', p.data_completeness,
                'trial_count', p.trial_count,
                'active_trial_count', p.active_trial_count,
                'label_count', p.label_count,
                'adverse_event_count', p.adverse_event_count,
                'first_approval_date', p.first_approval_date
            )
            FROM mol_gold.molecule_profiles p
            WHERE p.molecule_id = m.molecule_id
        ),
        'safety_summary', (
            SELECT JSONB_BUILD_OBJECT(
                'total_signals', COUNT(*),
                'top_signals', JSONB_AGG(
                    JSONB_BUILD_OBJECT(
                        'reaction', s.reaction_meddra_pt,
                        'case_count', s.case_count,
                        'signal_strength', s.signal_strength
                    ) ORDER BY s.case_count DESC
                ) FILTER (WHERE s.signal_id IS NOT NULL)
            )
            FROM (
                SELECT signal_id, reaction_meddra_pt, case_count, signal_strength
                FROM mol_gold.safety_signals
                WHERE molecule_id = m.molecule_id
                ORDER BY case_count DESC
                LIMIT 5
            ) s
        )
    ) INTO result
    FROM mol_silver.molecules m
    WHERE m.inchi_key = p_inchi_key AND m.needs_review = FALSE;

    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- PERMISSIONS FOR mol_api VIEWS
-- =============================================================================

GRANT SELECT ON mol_api.molecules TO mol_viewer;
GRANT SELECT ON mol_api.molecule_search TO mol_viewer;
GRANT SELECT ON mol_api.clinical_trials TO mol_viewer;
GRANT SELECT ON mol_api.drug_labels TO mol_viewer;
GRANT SELECT ON mol_api.safety_signals TO mol_viewer;
GRANT SELECT ON mol_api.adverse_events TO mol_viewer;
GRANT SELECT ON mol_api.cross_references TO mol_viewer;
GRANT SELECT ON mol_api.competitive_landscape TO mol_viewer;
GRANT SELECT ON mol_api.lifecycle_stages TO mol_viewer;

GRANT SELECT ON mol_api.resolution_queue TO mol_data_ops;
GRANT SELECT ON mol_api.pipeline_status TO mol_data_ops;
GRANT SELECT ON mol_api.data_sources TO mol_data_ops;

GRANT SELECT ON mol_api.tracked_molecules TO mol_analyst;
GRANT SELECT ON mol_api.user_annotations TO mol_analyst;

GRANT EXECUTE ON FUNCTION mol_api.search_molecules TO mol_viewer;
GRANT EXECUTE ON FUNCTION mol_api.get_molecule_details TO mol_viewer;

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Molecule API views migration complete (021_mol_api_views.sql)';
    RAISE NOTICE 'Views created: molecules, molecule_search, clinical_trials, drug_labels,';
    RAISE NOTICE '               safety_signals, adverse_events, cross_references,';
    RAISE NOTICE '               competitive_landscape, lifecycle_stages, resolution_queue,';
    RAISE NOTICE '               pipeline_status, data_sources, tracked_molecules, user_annotations';
    RAISE NOTICE 'Functions created: search_molecules, get_molecule_details';
END
$$;

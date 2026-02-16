-- Migration: 051_dynamic_transformation_config.sql
-- Purpose: Configuration tables for dynamic Bronze→Silver transformation
-- Enables zero-code onboarding of new data sources with SQLMesh integration
-- Date: 2026-01-28

BEGIN;

-- ============================================================================
-- SECTION 1: SILVER TRANSFORMATION RULES
-- ============================================================================
-- Defines how each source transforms from Bronze to Silver layer

CREATE TABLE IF NOT EXISTS raw.silver_transformation_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Source identification
    source_name TEXT NOT NULL UNIQUE,           -- e.g., 'new_pharma_db'
    source_table TEXT NOT NULL,                 -- e.g., 'bronze.new_pharma_db'

    -- Target configuration
    target_table TEXT NOT NULL DEFAULT 'silver.molecules',  -- Primary target
    target_type TEXT NOT NULL DEFAULT 'molecule',           -- molecule, trial, publication, target

    -- Column mappings: Bronze column → Silver column
    -- Format: {"bronze_col": "silver_col", "nested->>'field'": "silver_col", ...}
    column_mappings JSONB NOT NULL DEFAULT '{}',

    -- Computed columns (SQL expressions)
    -- Format: {"silver_col": "COALESCE(col1, col2)", "status": "CASE WHEN..."}
    computed_columns JSONB DEFAULT '{}',

    -- Identifier extraction rules
    -- Format: {"identifier_type": "json_path_or_column", ...}
    -- e.g., {"drugbank_id": "external_ids->>'drugbank'", "chembl_id": "chembl_id"}
    identifier_mappings JSONB DEFAULT '{}',

    -- Name extraction for drug_name_lookup
    -- Format: {"generic": "col_or_path", "brand": "brands_array", "synonyms": "synonyms_jsonb"}
    name_mappings JSONB DEFAULT '{}',

    -- Deduplication strategy
    dedup_strategy TEXT NOT NULL DEFAULT 'inchi_key',  -- inchi_key, identifier_match, name_fuzzy, composite
    dedup_columns JSONB DEFAULT '["inchi_key"]',       -- Columns to use for dedup
    dedup_confidence_threshold NUMERIC(3,2) DEFAULT 0.80,

    -- Source precedence (lower = higher priority for conflicts)
    source_precedence INTEGER NOT NULL DEFAULT 10,

    -- Incremental processing
    incremental_column TEXT DEFAULT 'source_updated_at',  -- Column to track for incremental
    batch_size INTEGER DEFAULT 1000,

    -- Filtering
    where_clause TEXT,  -- Optional WHERE clause for source filtering

    -- Status
    enabled BOOLEAN DEFAULT true,
    last_run_at TIMESTAMPTZ,
    last_run_records INTEGER,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,

    CONSTRAINT valid_target_type CHECK (target_type IN ('molecule', 'trial', 'publication', 'target', 'adverse_event', 'patent'))
);

CREATE INDEX IF NOT EXISTS idx_silver_rules_source ON raw.silver_transformation_rules(source_name);
CREATE INDEX IF NOT EXISTS idx_silver_rules_enabled ON raw.silver_transformation_rules(enabled) WHERE enabled = true;

-- ============================================================================
-- SECTION 2: IDENTIFIER EXTRACTION PATTERNS
-- ============================================================================
-- Defines regex patterns and extraction rules for each identifier type per source

CREATE TABLE IF NOT EXISTS raw.source_identifier_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    source_name TEXT NOT NULL,
    identifier_type TEXT NOT NULL,  -- References raw.identifier_types.identifier_type

    -- Extraction configuration
    source_column TEXT NOT NULL,           -- Column in Bronze table
    extraction_method TEXT DEFAULT 'direct', -- direct, json_path, regex, split
    extraction_config JSONB,               -- Method-specific config

    -- Validation
    validation_regex TEXT,                 -- Regex to validate extracted value
    transform_sql TEXT,                    -- Optional SQL transformation

    -- Priority (for sources with multiple columns for same identifier)
    priority INTEGER DEFAULT 1,

    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source_name, identifier_type, source_column)
);

CREATE INDEX IF NOT EXISTS idx_source_id_patterns_source ON raw.source_identifier_patterns(source_name);

-- ============================================================================
-- SECTION 3: TRANSFORMATION TEMPLATES
-- ============================================================================
-- Reusable transformation templates for common patterns

CREATE TABLE IF NOT EXISTS raw.transformation_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    template_name TEXT NOT NULL UNIQUE,
    description TEXT,

    -- Template type
    template_type TEXT NOT NULL,  -- column_mapping, identifier_extraction, name_extraction, full

    -- Template content (Jinja2 format for SQLMesh)
    template_sql TEXT NOT NULL,

    -- Required parameters
    required_params JSONB DEFAULT '[]',

    -- Example usage
    example_config JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- SECTION 4: GENERATED MODEL REGISTRY
-- ============================================================================
-- Tracks generated SQLMesh models for audit and regeneration

CREATE TABLE IF NOT EXISTS raw.generated_sqlmesh_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    model_name TEXT NOT NULL UNIQUE,        -- e.g., 'silver.new_pharma_molecules'
    source_rule_id UUID REFERENCES raw.silver_transformation_rules(id),

    -- Generated content
    model_sql TEXT NOT NULL,                -- The generated SQL
    model_hash TEXT NOT NULL,               -- SHA256 of the SQL for change detection

    -- File location
    file_path TEXT NOT NULL,                -- Relative path in sqlmesh/models/

    -- Status
    generation_status TEXT DEFAULT 'generated',  -- generated, applied, error
    last_generated_at TIMESTAMPTZ DEFAULT NOW(),
    last_applied_at TIMESTAMPTZ,

    -- Error tracking
    last_error TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_models_rule ON raw.generated_sqlmesh_models(source_rule_id);

-- ============================================================================
-- SECTION 5: INSERT DEFAULT TEMPLATES
-- ============================================================================

INSERT INTO raw.transformation_templates (template_name, description, template_type, template_sql, required_params, example_config)
VALUES
-- Molecule transformation template
('molecule_transform', 'Standard molecule transformation from Bronze to Silver', 'full',
$TEMPLATE$
-- SQLMesh Model: Silver {{ source_name }} Molecules
-- Auto-generated from transformation rules
-- Source: {{ source_table }}

MODEL (
    name silver.{{ source_name }}_molecules,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key inchi_key,
        when_matched_update_all TRUE
    ),
    cron '{{ cron_schedule }}',
    grain inchi_key
);

WITH source_data AS (
    SELECT
        {{ column_mappings | join(',\n        ') }}
    FROM {{ source_table }}
    WHERE processed_to_silver = FALSE
    {% if where_clause %}AND {{ where_clause }}{% endif %}
    {% if incremental_column %}AND {{ incremental_column }} BETWEEN @start_dt AND @end_dt{% endif %}
),

deduplicated AS (
    SELECT DISTINCT ON ({{ dedup_columns | join(', ') }})
        gen_random_uuid() AS id,
        *,
        {{ source_precedence }} AS source_precedence,
        '{{ source_name }}' AS primary_source,
        NOW() AS created_at,
        NOW() AS updated_at
    FROM source_data
    WHERE {{ dedup_columns[0] }} IS NOT NULL
    ORDER BY {{ dedup_columns | join(', ') }}, source_updated_at DESC
)

SELECT * FROM deduplicated;
$TEMPLATE$,
'["source_name", "source_table", "column_mappings", "dedup_columns"]',
'{"source_name": "new_db", "source_table": "bronze.new_db", "column_mappings": ["inchi_key", "name AS canonical_name"], "dedup_columns": ["inchi_key"]}'
),

-- Identifier extraction template
('identifier_extraction', 'Extract identifiers from source to silver.identifier_mappings', 'identifier_extraction',
$TEMPLATE$
-- Identifier extraction for {{ source_name }}
SELECT
    m.id AS molecule_id,
    '{{ identifier_type }}' AS identifier_type,
    {{ extraction_expression }} AS identifier_value,
    '{{ source_name }}' AS source,
    {{ confidence }} AS confidence,
    {{ is_primary }} AS is_primary,
    s.source_updated_at AS source_date,
    NOW() AS created_at
FROM silver.molecules m
JOIN {{ source_table }} s ON m.inchi_key = s.inchi_key
WHERE {{ extraction_expression }} IS NOT NULL
  AND m.needs_review = FALSE
$TEMPLATE$,
'["source_name", "source_table", "identifier_type", "extraction_expression"]',
'{"identifier_type": "drugbank_id", "extraction_expression": "s.drugbank_id"}'
),

-- Name lookup template
('name_lookup', 'Extract drug names for silver.drug_name_lookup', 'name_extraction',
$TEMPLATE$
-- Name extraction for {{ source_name }}
{% for name_type, column_expr in name_mappings.items() %}
SELECT
    m.id AS molecule_id,
    {{ column_expr }} AS name,
    '{{ name_type }}' AS name_type,
    LOWER(TRIM({{ column_expr }})) AS name_normalized,
    '{{ source_name }}' AS source,
    NOW() AS created_at
FROM silver.molecules m
JOIN {{ source_table }} s ON m.inchi_key = s.inchi_key
WHERE {{ column_expr }} IS NOT NULL
  AND m.needs_review = FALSE
{% if not loop.last %}UNION ALL{% endif %}
{% endfor %}
$TEMPLATE$,
'["source_name", "source_table", "name_mappings"]',
'{"name_mappings": {"generic": "s.drug_name", "brand": "s.brand_name"}}'
)
ON CONFLICT (template_name) DO NOTHING;

-- ============================================================================
-- SECTION 6: INSERT EXISTING SOURCE RULES (migrate current hardcoded logic)
-- ============================================================================

-- DrugBank transformation rule
INSERT INTO raw.silver_transformation_rules (
    source_name, source_table, target_table, target_type,
    column_mappings, identifier_mappings, name_mappings,
    dedup_strategy, dedup_columns, source_precedence
) VALUES (
    'drugbank',
    'bronze.drugbank',
    'silver.molecules',
    'molecule',
    '{
        "inchi_key": "inchi_key",
        "name": "canonical_name",
        "smiles": "canonical_smiles",
        "inchi": "inchi",
        "molecular_formula": "molecular_formula",
        "average_mass": "molecular_weight",
        "drug_type": "molecule_type",
        "mechanism_of_action": "mechanism_of_action",
        "indication": "therapeutic_areas"
    }',
    '{
        "drugbank_id": "drugbank_id",
        "cas_number": "cas_number",
        "unii": "unii"
    }',
    '{
        "generic": "name",
        "synonyms": "synonyms",
        "brand": "international_brands"
    }',
    'inchi_key',
    '["inchi_key"]',
    1
) ON CONFLICT (source_name) DO NOTHING;

-- ChEMBL transformation rule
INSERT INTO raw.silver_transformation_rules (
    source_name, source_table, target_table, target_type,
    column_mappings, identifier_mappings, name_mappings,
    dedup_strategy, dedup_columns, source_precedence
) VALUES (
    'chembl',
    'bronze.chembl_molecules',
    'silver.molecules',
    'molecule',
    '{
        "inchi_key": "inchi_key",
        "pref_name": "canonical_name",
        "canonical_smiles": "canonical_smiles",
        "inchi": "inchi",
        "molecular_formula": "molecular_formula",
        "molecular_weight": "molecular_weight",
        "molecule_type": "molecule_type",
        "max_phase": "max_phase",
        "first_approval": "first_approval_year"
    }',
    '{
        "chembl_id": "chembl_id"
    }',
    '{
        "generic": "pref_name",
        "synonyms": "synonyms"
    }',
    'inchi_key',
    '["inchi_key"]',
    2
) ON CONFLICT (source_name) DO NOTHING;

-- PubChem transformation rule
INSERT INTO raw.silver_transformation_rules (
    source_name, source_table, target_table, target_type,
    column_mappings, identifier_mappings, name_mappings,
    dedup_strategy, dedup_columns, source_precedence
) VALUES (
    'pubchem',
    'bronze.pubchem',
    'silver.molecules',
    'molecule',
    '{
        "inchi_key": "inchi_key",
        "iupac_name": "canonical_name",
        "canonical_smiles": "canonical_smiles",
        "inchi": "inchi",
        "molecular_formula": "molecular_formula",
        "molecular_weight": "molecular_weight"
    }',
    '{
        "pubchem_cid": "cid"
    }',
    '{
        "generic": "iupac_name"
    }',
    'inchi_key',
    '["inchi_key"]',
    3
) ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- SECTION 7: AUDIT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION raw.update_transformation_rule_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_transformation_rule ON raw.silver_transformation_rules;
CREATE TRIGGER trigger_update_transformation_rule
    BEFORE UPDATE ON raw.silver_transformation_rules
    FOR EACH ROW
    EXECUTE FUNCTION raw.update_transformation_rule_timestamp();

COMMIT;

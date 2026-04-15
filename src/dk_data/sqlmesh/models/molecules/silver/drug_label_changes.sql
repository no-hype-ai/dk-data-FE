-- SQLMesh Model: Silver Drug Label Changes
-- Computes section-level diffs between consecutive SPL versions per set_id.
-- Uses LAG() window function to compare each label section between the current
-- and previous version, outputting one row per changed section.
-- Feature: 006-claims-engine-data-gaps (T020)

MODEL (
    name mol_silver.drug_label_changes,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (set_id, section_name, change_type))
    ),
    grain (set_id, from_version, to_version, section_name)
);

-- All label versions ordered by (set_id, spl_version) with LAG for previous version.
-- We read from mol_bronze.openfda_labels which has one row per (set_id, spl_version).
WITH versioned_labels AS (
    SELECT
        set_id,
        spl_version,
        LAG(spl_version) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_version,
        -- Label sections (TEXT columns)
        indications_and_usage,
        LAG(indications_and_usage) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_indications_and_usage,
        dosage_and_administration,
        LAG(dosage_and_administration) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_dosage_and_administration,
        contraindications,
        LAG(contraindications) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_contraindications,
        warnings,
        LAG(warnings) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_warnings,
        warnings_and_cautions,
        LAG(warnings_and_cautions) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_warnings_and_cautions,
        boxed_warning,
        LAG(boxed_warning) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_boxed_warning,
        adverse_reactions,
        LAG(adverse_reactions) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_adverse_reactions,
        drug_interactions,
        LAG(drug_interactions) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_drug_interactions,
        use_in_specific_populations,
        LAG(use_in_specific_populations) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_use_in_specific_populations,
        clinical_pharmacology,
        LAG(clinical_pharmacology) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_clinical_pharmacology,
        mechanism_of_action,
        LAG(mechanism_of_action) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_mechanism_of_action,
        pharmacodynamics,
        LAG(pharmacodynamics) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_pharmacodynamics,
        pharmacokinetics,
        LAG(pharmacokinetics) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_pharmacokinetics,
        overdosage,
        LAG(overdosage) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_overdosage,
        description,
        LAG(description) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_description,
        clinical_studies,
        LAG(clinical_studies) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_clinical_studies,
        how_supplied,
        LAG(how_supplied) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_how_supplied,
        storage_and_handling,
        LAG(storage_and_handling) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_storage_and_handling,
        pregnancy,
        LAG(pregnancy) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_pregnancy,
        nursing_mothers,
        LAG(nursing_mothers) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_nursing_mothers,
        pediatric_use,
        LAG(pediatric_use) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_pediatric_use,
        geriatric_use,
        LAG(geriatric_use) OVER (PARTITION BY set_id ORDER BY spl_version) AS prev_geriatric_use,
        source_updated_at
    FROM mol_bronze.openfda_labels
    WHERE set_id IS NOT NULL
),

-- Only rows that have a previous version (i.e., skip the first version per set_id)
with_prev AS (
    SELECT * FROM versioned_labels
    WHERE prev_version IS NOT NULL
),

-- UNNEST each section into rows and compare current vs previous
section_diffs AS (
    SELECT
        set_id,
        prev_version    AS from_version,
        spl_version     AS to_version,
        section_name,
        prev_text,
        curr_text,
        source_updated_at
    FROM with_prev
    CROSS JOIN LATERAL (
        VALUES
            ('indications_and_usage',       prev_indications_and_usage,       indications_and_usage),
            ('dosage_and_administration',    prev_dosage_and_administration,   dosage_and_administration),
            ('contraindications',           prev_contraindications,           contraindications),
            ('warnings',                    prev_warnings,                    warnings),
            ('warnings_and_cautions',       prev_warnings_and_cautions,       warnings_and_cautions),
            ('boxed_warning',               prev_boxed_warning,               boxed_warning),
            ('adverse_reactions',           prev_adverse_reactions,           adverse_reactions),
            ('drug_interactions',           prev_drug_interactions,           drug_interactions),
            ('use_in_specific_populations', prev_use_in_specific_populations, use_in_specific_populations),
            ('clinical_pharmacology',       prev_clinical_pharmacology,       clinical_pharmacology),
            ('mechanism_of_action',         prev_mechanism_of_action,         mechanism_of_action),
            ('pharmacodynamics',            prev_pharmacodynamics,            pharmacodynamics),
            ('pharmacokinetics',            prev_pharmacokinetics,            pharmacokinetics),
            ('overdosage',                  prev_overdosage,                  overdosage),
            ('description',                 prev_description,                 description),
            ('clinical_studies',            prev_clinical_studies,            clinical_studies),
            ('how_supplied',                prev_how_supplied,                how_supplied),
            ('storage_and_handling',        prev_storage_and_handling,        storage_and_handling),
            ('pregnancy',                   prev_pregnancy,                   pregnancy),
            ('nursing_mothers',             prev_nursing_mothers,             nursing_mothers),
            ('pediatric_use',               prev_pediatric_use,               pediatric_use),
            ('geriatric_use',               prev_geriatric_use,               geriatric_use)
    ) AS sections(section_name, prev_text, curr_text)
    -- Only emit rows where the section actually changed
    WHERE NOT (prev_text IS NOT DISTINCT FROM curr_text)
)

SELECT
    gen_random_uuid()           AS id,
    set_id,
    from_version,
    to_version,
    section_name,
    CASE
        WHEN prev_text IS NULL AND curr_text IS NOT NULL THEN 'added'
        WHEN prev_text IS NOT NULL AND curr_text IS NULL THEN 'removed'
        ELSE 'modified'
    END                         AS change_type,
    -- diff_text: for added sections show new text; for removed show old text;
    -- for modified show new text (full text comparison — downstream consumers
    -- can compute word-level diffs if needed).
    CASE
        WHEN prev_text IS NULL AND curr_text IS NOT NULL THEN curr_text
        WHEN prev_text IS NOT NULL AND curr_text IS NULL THEN prev_text
        ELSE curr_text
    END                         AS diff_text,
    source_updated_at           AS detected_at
FROM section_diffs;

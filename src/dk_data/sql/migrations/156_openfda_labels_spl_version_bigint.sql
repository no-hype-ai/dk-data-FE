-- Migration 156: alter mol_bronze.openfda_labels.spl_version from INTEGER to BIGINT
-- SPL version values can exceed INT32 max (2,147,483,647); e.g. 4,571,261,921 observed.
-- The physical SQLMesh table is mol_bronze.mol_bronze__openfda_labels__1964078876;
-- the view mol_bronze.openfda_labels must be dropped and recreated to allow the ALTER.
DO $$
BEGIN
    -- Only run if column is still integer
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'mol_bronze'
          AND table_name = 'mol_bronze__openfda_labels__1964078876'
          AND column_name = 'spl_version'
          AND data_type = 'integer'
    ) THEN
        DROP VIEW IF EXISTS mol_bronze.openfda_labels;
        ALTER TABLE mol_bronze."mol_bronze__openfda_labels__1964078876"
            ALTER COLUMN spl_version TYPE BIGINT;
        CREATE VIEW mol_bronze.openfda_labels AS
            SELECT id, set_id, spl_version, spl_id, brand_name, generic_name, manufacturer_name, product_type,
                   routes, dosage_forms, pharm_class_epc, pharm_class_moa, rxcui, unii, spl_set_ids, nui,
                   application_numbers, effective_date, indications_and_usage, dosage_and_administration,
                   contraindications, warnings, warnings_and_cautions, boxed_warning, adverse_reactions,
                   drug_interactions, use_in_specific_populations, clinical_pharmacology, mechanism_of_action,
                   pharmacodynamics, pharmacokinetics, overdosage, description, clinical_studies, how_supplied,
                   storage_and_handling, principal_display_panel, pregnancy, nursing_mothers, pediatric_use,
                   geriatric_use, has_boxed_warning, is_original_packager, raw_json, raw_source_id, source,
                   request_timestamp, source_updated_at, processed_to_silver, created_at
            FROM mol_bronze."mol_bronze__openfda_labels__1964078876";
    END IF;
END $$;

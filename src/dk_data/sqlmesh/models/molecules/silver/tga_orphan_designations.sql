-- SQLMesh Model: Silver TGA Orphan Drug Designations
-- Three resolve_* calls: molecule (active ingredient), company (sponsor),
-- condition (intended indication). Each is named-param per skill.
-- Grain: (designation_number, designation_date)

MODEL (
    name mol_silver.tga_orphan_designations,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (designation_number, designation_date)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (designation_number))
    ),
    grain (designation_number, designation_date)
);

SELECT
    -- Entity-resolved FKs
    mol_silver.resolve_molecule(
        p_name => b.active_ingredient
    )                                                                AS molecule_id,

    mol_silver.resolve_company(
        p_name => b.sponsor_name
    )                                                                AS company_id,

    ind_silver.resolve_condition(
        p_name => COALESCE(b.orphan_condition, b.intended_indication)
    )                                                                AS condition_id,

    -- Natural key
    b.designation_number,
    b.designation_date,

    -- Identity
    b.active_ingredient,
    b.product_name,
    b.sponsor_name,

    -- Indication (retained strings)
    b.intended_indication,
    b.orphan_condition,

    -- Status
    b.status,

    -- Raw tracking
    b.raw_source_id,
    b.source                                                         AS source_id,
    b.source_updated_at,
    NOW()                                                            AS silver_loaded_at

FROM mol_bronze.tga_orphan_designations AS b
WHERE b.processed_to_silver = FALSE
  AND b.designation_number IS NOT NULL;

-- SQLMesh Model: hcs_silver.open_payments_drug_linkage
-- Links CMS Open Payments (Sunshine Act) payment records to mol_silver.molecules.
--
-- Closes Gap 4 from ENTITY_LINKING_STRATEGY.md:
--   "CMS Open Payments drug names not linked — Payment data isolated from molecule graph"
--
-- Entity linking strategy (two paths, in priority order):
--   Path A (NDC → molecule_id, confidence 0.95):
--     associated_drug_or_biological_ndc_N → mol_silver.molecule_identifiers (source='ndc')
--     NDC is a structural identifier; high confidence.
--
--   Path B (drug name → normalized_name → molecule_id, confidence 0.75):
--     drug_name_N → mol_silver.molecule_names (normalized_name equi-join)
--     Brand/trade names appear in Open Payments; molecule_names covers brand names.
--
-- Grain: (record_id, drug_slot, _source_year)
--   We UNNEST the 5 drug slots so each drug in a payment gets its own row.
--   drug_slot ∈ {1, 2, 3, 4, 5} identifies which slot the link came from.
--   Records with no drug (not a drug payment) are excluded (WHERE drug_name IS NOT NULL).
--
-- Column name notes:
--   CMS raw drug name field: name_of_drug_or_biological_or_device_or_medical_supply_N
--   Normalized variant (GENERATED ALWAYS on raw): drug_name_N_normalized
--
-- Upstream: hcs_silver.open_payments_drug_linkage → hcs_gold for:
--   • "Total industry payments for drug X by manufacturer"
--   • "Which physicians received payments for drug X?"
--   • Cross-reference: prescriber payments vs. Part D prescribing volume
--
-- Feature: 001-silver-medallion-rebuild (updated from 020-entity-linking-gaps)

MODEL (
    name hcs_silver.open_payments_drug_linkage,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (record_id, drug_slot, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (record_id, drug_slot, _source_year, drug_name))
    ),
    grain (record_id, drug_slot, _source_year),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

-- ── Explode the 5 drug slots into one row per drug per payment ───────────────
WITH payment_drugs AS (
    -- Slot 1
    SELECT
        record_id,
        1                                                           AS drug_slot,
        name_of_drug_or_biological_or_device_or_medical_supply_1   AS drug_name,
        drug_name_1_normalized                                      AS drug_name_normalized,
        associated_drug_or_biological_ndc_1                        AS ndc,
        covered_recipient_type,
        physician_profile_id,
        physician_first_name,
        physician_last_name,
        physician_specialty,
        applicable_manufacturer_or_gpo_name,
        total_amount_of_payment_usdollars,
        number_of_payments_included_in_total_amount,
        form_of_payment_or_transfer_of_value,
        date_of_payment,
        nature_of_payment_or_transfer_of_value,
        recipient_city,
        recipient_state,
        recipient_zip_code,
        program_year,
        payment_publication_date,
        _source_year,
        _source_hash
    FROM hcs_bronze.cms_open_payments
    WHERE name_of_drug_or_biological_or_device_or_medical_supply_1 IS NOT NULL

    UNION ALL

    -- Slot 2
    SELECT record_id, 2,
           name_of_drug_or_biological_or_device_or_medical_supply_2,
           drug_name_2_normalized, associated_drug_or_biological_ndc_2,
           covered_recipient_type, physician_profile_id, physician_first_name,
           physician_last_name, physician_specialty, applicable_manufacturer_or_gpo_name,
           total_amount_of_payment_usdollars,
           number_of_payments_included_in_total_amount,
           form_of_payment_or_transfer_of_value,
           date_of_payment,
           nature_of_payment_or_transfer_of_value,
           recipient_city, recipient_state, recipient_zip_code,
           program_year, payment_publication_date, _source_year, _source_hash
    FROM hcs_bronze.cms_open_payments
    WHERE name_of_drug_or_biological_or_device_or_medical_supply_2 IS NOT NULL

    UNION ALL

    -- Slot 3
    SELECT record_id, 3,
           name_of_drug_or_biological_or_device_or_medical_supply_3,
           drug_name_3_normalized, associated_drug_or_biological_ndc_3,
           covered_recipient_type, physician_profile_id, physician_first_name,
           physician_last_name, physician_specialty, applicable_manufacturer_or_gpo_name,
           total_amount_of_payment_usdollars,
           number_of_payments_included_in_total_amount,
           form_of_payment_or_transfer_of_value,
           date_of_payment,
           nature_of_payment_or_transfer_of_value,
           recipient_city, recipient_state, recipient_zip_code,
           program_year, payment_publication_date, _source_year, _source_hash
    FROM hcs_bronze.cms_open_payments
    WHERE name_of_drug_or_biological_or_device_or_medical_supply_3 IS NOT NULL

    UNION ALL

    -- Slot 4
    SELECT record_id, 4,
           name_of_drug_or_biological_or_device_or_medical_supply_4,
           drug_name_4_normalized, associated_drug_or_biological_ndc_4,
           covered_recipient_type, physician_profile_id, physician_first_name,
           physician_last_name, physician_specialty, applicable_manufacturer_or_gpo_name,
           total_amount_of_payment_usdollars,
           number_of_payments_included_in_total_amount,
           form_of_payment_or_transfer_of_value,
           date_of_payment,
           nature_of_payment_or_transfer_of_value,
           recipient_city, recipient_state, recipient_zip_code,
           program_year, payment_publication_date, _source_year, _source_hash
    FROM hcs_bronze.cms_open_payments
    WHERE name_of_drug_or_biological_or_device_or_medical_supply_4 IS NOT NULL

    UNION ALL

    -- Slot 5
    SELECT record_id, 5,
           name_of_drug_or_biological_or_device_or_medical_supply_5,
           drug_name_5_normalized, associated_drug_or_biological_ndc_5,
           covered_recipient_type, physician_profile_id, physician_first_name,
           physician_last_name, physician_specialty, applicable_manufacturer_or_gpo_name,
           total_amount_of_payment_usdollars,
           number_of_payments_included_in_total_amount,
           form_of_payment_or_transfer_of_value,
           date_of_payment,
           nature_of_payment_or_transfer_of_value,
           recipient_city, recipient_state, recipient_zip_code,
           program_year, payment_publication_date, _source_year, _source_hash
    FROM hcs_bronze.cms_open_payments
    WHERE name_of_drug_or_biological_or_device_or_medical_supply_5 IS NOT NULL
)

-- ── Final output: LATERAL joins for molecule resolution ───────────────────────
SELECT
    gen_random_uuid()                           AS id,

    -- Payment identity
    pd.record_id,
    pd.drug_slot,
    pd._source_year,

    -- Molecule resolution (NDC path takes priority over name path)
    COALESCE(ndc_link.molecule_id, name_link.molecule_id) AS molecule_id,
    CASE
        WHEN ndc_link.molecule_id  IS NOT NULL THEN 0.95
        WHEN name_link.molecule_id IS NOT NULL THEN 0.75
        ELSE NULL
    END                                         AS link_confidence,
    CASE
        WHEN ndc_link.molecule_id  IS NOT NULL THEN 'ndc'
        WHEN name_link.molecule_id IS NOT NULL THEN 'name'
        ELSE NULL
    END                                         AS link_strategy,
    CASE
        WHEN COALESCE(ndc_link.molecule_id, name_link.molecule_id) IS NOT NULL
        THEN TRUE ELSE FALSE
    END                                         AS molecule_resolved,

    -- Drug data (raw + normalized)
    pd.drug_name,
    pd.drug_name_normalized,
    pd.ndc,

    -- Recipient / provider context
    pd.covered_recipient_type,
    pd.physician_profile_id,
    pd.physician_first_name,
    pd.physician_last_name,
    pd.physician_specialty,
    pd.recipient_state,

    -- Payment details
    pd.applicable_manufacturer_or_gpo_name,
    pd.total_amount_of_payment_usdollars,
    pd.number_of_payments_included_in_total_amount,
    pd.form_of_payment_or_transfer_of_value,
    pd.date_of_payment,
    pd.nature_of_payment_or_transfer_of_value,
    pd.recipient_city,
    pd.recipient_zip_code,
    pd.program_year,
    pd.payment_publication_date,
    pd._source_hash,

    'cms_open_payments'                         AS source,
    NOW()                                       AS source_updated_at,
    NOW()                                       AS created_at,
    NOW()                                       AS updated_at

FROM payment_drugs pd

-- Path A: NDC → mol_silver.molecule_identifiers (indexed equi-join, no wildcards)
LEFT JOIN LATERAL (
    SELECT mi.molecule_id
    FROM mol_silver.molecule_identifiers mi
    WHERE mi.source = 'ndc'
      AND mi.identifier = pd.ndc
    ORDER BY mi.molecule_id
    LIMIT 1
) ndc_link ON TRUE

-- Path B: drug name → mol_silver.molecule_names (indexed equi-join on normalized_name)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE pd.drug_name IS NOT NULL
      AND LENGTH(pd.drug_name_normalized) >= 4
      AND mn.normalized_name = pd.drug_name_normalized
    ORDER BY mn.molecule_id
    LIMIT 1
) name_link ON TRUE;

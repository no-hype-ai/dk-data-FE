-- SQLMesh Model: hcs_silver.open_payments_drug_linkage
-- Links CMS Open Payments (Sunshine Act) payment records to mol_silver.molecules.
--
-- Closes Gap 4 from ENTITY_LINKING_STRATEGY.md:
--   "CMS Open Payments drug names not linked — Payment data isolated from molecule graph"
--
-- Entity linking strategy (two paths, in priority order):
--   Path A (NDC → molecule_id, confidence 0.95):
--     associated_drug_or_biological_ndc_N → mol_silver.ndc_molecule_bridge → molecule_id
--     NDC is a structural identifier; same confidence level as identifier_mappings.ndc.
--
--   Path B (drug name → alias → molecule_id, confidence 0.75):
--     drug_name_N_normalized → mol_silver.molecule_aliases.alias_name_normalized
--     Brand/trade names appear in Open Payments; alias table covers brand names.
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
-- Feature: 020-entity-linking-gaps

MODEL (
    name hcs_silver.open_payments_drug_linkage,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (record_id, drug_slot, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (record_id, drug_slot, _source_year, drug_name))
    ),
    grain (record_id, drug_slot, _source_year)
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
        _source_year
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
           program_year, payment_publication_date, _source_year
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
           program_year, payment_publication_date, _source_year
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
           program_year, payment_publication_date, _source_year
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
           program_year, payment_publication_date, _source_year
    FROM hcs_bronze.cms_open_payments
    WHERE name_of_drug_or_biological_or_device_or_medical_supply_5 IS NOT NULL
),

-- ── Path A: NDC → molecule_id (confidence 0.95) ──────────────────────────────
ndc_linked AS (
    SELECT
        pd.record_id,
        pd.drug_slot,
        pd._source_year,
        nb.molecule_id,
        0.95 AS link_confidence,
        'ndc'::TEXT AS link_strategy
    FROM payment_drugs pd
    JOIN mol_silver.ndc_molecule_bridge nb
        -- NDC format: strip dashes, match on raw NDC value
        ON REPLACE(pd.ndc, '-', '') = REPLACE(nb.ndc, '-', '')
    WHERE pd.ndc IS NOT NULL
),

-- ── Path B: drug name → alias → molecule_id (confidence 0.75) ────────────────
alias_linked AS (
    SELECT
        pd.record_id,
        pd.drug_slot,
        pd._source_year,
        ma.molecule_id,
        0.75 AS link_confidence,
        'alias'::TEXT AS link_strategy
    FROM payment_drugs pd
    JOIN mol_silver.molecule_aliases ma
        ON pd.drug_name_normalized = ma.alias_name_normalized
    WHERE pd.drug_name_normalized IS NOT NULL
      AND LENGTH(pd.drug_name_normalized) >= 4
      -- Only use alias path when NDC path didn't resolve
      AND NOT EXISTS (
          SELECT 1 FROM ndc_linked nl
          WHERE nl.record_id    = pd.record_id
            AND nl.drug_slot    = pd.drug_slot
            AND nl._source_year = pd._source_year
      )
),

-- ── Combine both paths (NDC takes priority) ───────────────────────────────────
molecule_links AS (
    SELECT * FROM ndc_linked
    UNION ALL
    SELECT * FROM alias_linked
),

-- Deduplicate: if somehow both paths hit, keep NDC (highest confidence)
best_link AS (
    SELECT DISTINCT ON (record_id, drug_slot, _source_year)
        record_id,
        drug_slot,
        _source_year,
        molecule_id,
        link_confidence,
        link_strategy
    FROM molecule_links
    ORDER BY record_id, drug_slot, _source_year, link_confidence DESC
)

-- ── Final output ──────────────────────────────────────────────────────────────
SELECT
    gen_random_uuid()                           AS id,

    -- Payment identity
    pd.record_id,
    pd.drug_slot,
    pd._source_year,

    -- Molecule resolution
    bl.molecule_id,                             -- NULL when neither path matched
    bl.link_confidence,
    bl.link_strategy,
    CASE WHEN bl.molecule_id IS NOT NULL THEN TRUE ELSE FALSE END AS molecule_resolved,

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

    NOW()                                       AS created_at,
    NOW()                                       AS updated_at

FROM payment_drugs pd
LEFT JOIN best_link bl
    ON pd.record_id     = bl.record_id
   AND pd.drug_slot     = bl.drug_slot
   AND pd._source_year  = bl._source_year;

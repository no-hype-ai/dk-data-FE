-- Migration 083: CMS PUF Raw Tables (016-cms-puf-datasource-integration)
-- Purpose: Create 30 hcs_raw.cms_* tables for CMS Public Use File ingestion
-- Date: 2026-03-11

BEGIN;

-- =============================================================================
-- PROVIDER GROUP (7 tables)
-- =============================================================================

-- hcs_raw.cms_nppes — National Plan and Provider Enumeration System
CREATE TABLE IF NOT EXISTS hcs_raw.cms_nppes (
    npi                 TEXT PRIMARY KEY,
    entity_type         TEXT,
    name_first          TEXT,
    name_last           TEXT,
    name_org            TEXT,
    credential          TEXT,
    taxonomy_code       TEXT,
    practice_address_1  TEXT,
    practice_city       TEXT,
    practice_state      TEXT,
    practice_zip        TEXT,
    practice_phone      TEXT,
    enumeration_date    DATE,
    last_updated        DATE,
    deactivation_date   DATE,
    gender              TEXT,
    _loaded_at          TIMESTAMPTZ DEFAULT now(),
    _source_file        TEXT,
    _source_hash        TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_nppes_state ON hcs_raw.cms_nppes (practice_state);
CREATE INDEX IF NOT EXISTS idx_cms_nppes_taxonomy ON hcs_raw.cms_nppes (taxonomy_code);
CREATE INDEX IF NOT EXISTS idx_cms_nppes_name_org ON hcs_raw.cms_nppes (name_org);

-- hcs_raw.cms_part_d_prescriber — Medicare Part D Prescriber PUF (partitioned by year)
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber (
    npi                     TEXT NOT NULL,
    drug_name               TEXT NOT NULL,
    generic_name            TEXT,
    total_claim_count       INTEGER,
    total_30_day_fill_count NUMERIC,
    total_drug_cost         NUMERIC,
    total_beneficiary_count INTEGER,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (npi, drug_name, year)
) PARTITION BY RANGE (year);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2019 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2019) TO (2020);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2020 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2020) TO (2021);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2021 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2021) TO (2022);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2022 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2022) TO (2023);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2023 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2023) TO (2024);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2024 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2024) TO (2025);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2025 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2025) TO (2026);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_prescriber_2026 PARTITION OF hcs_raw.cms_part_d_prescriber FOR VALUES FROM (2026) TO (2027);

CREATE INDEX IF NOT EXISTS idx_cms_part_d_prescriber_npi ON hcs_raw.cms_part_d_prescriber (npi);
CREATE INDEX IF NOT EXISTS idx_cms_part_d_prescriber_drug ON hcs_raw.cms_part_d_prescriber (generic_name);

-- hcs_raw.cms_physician_puf — Medicare Physician & Other Supplier PUF (partitioned by year)
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf (
    npi                         TEXT NOT NULL,
    hcpcs_code                  TEXT NOT NULL,
    hcpcs_description           TEXT,
    line_srvc_cnt               NUMERIC,
    bene_unique_cnt             INTEGER,
    avg_medicare_payment_amt    NUMERIC,
    year                        INTEGER NOT NULL,
    _loaded_at                  TIMESTAMPTZ DEFAULT now(),
    _source_file                TEXT,
    _source_hash                TEXT,
    PRIMARY KEY (npi, hcpcs_code, year)
) PARTITION BY RANGE (year);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2019 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2019) TO (2020);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2020 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2020) TO (2021);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2021 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2021) TO (2022);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2022 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2022) TO (2023);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2023 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2023) TO (2024);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2024 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2024) TO (2025);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2025 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2025) TO (2026);
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_2026 PARTITION OF hcs_raw.cms_physician_puf FOR VALUES FROM (2026) TO (2027);

CREATE INDEX IF NOT EXISTS idx_cms_physician_puf_npi ON hcs_raw.cms_physician_puf (npi);
CREATE INDEX IF NOT EXISTS idx_cms_physician_puf_hcpcs ON hcs_raw.cms_physician_puf (hcpcs_code);

-- hcs_raw.cms_open_payments_general — Open Payments General Payments
CREATE TABLE IF NOT EXISTS hcs_raw.cms_open_payments_general (
    record_id                   TEXT PRIMARY KEY,
    physician_npi               TEXT,
    payer_name                  TEXT,
    total_amount_of_payment     NUMERIC,
    nature_of_payment           TEXT,
    form_of_payment             TEXT,
    program_year                INTEGER,
    _loaded_at                  TIMESTAMPTZ DEFAULT now(),
    _source_file                TEXT,
    _source_hash                TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_open_payments_general_npi ON hcs_raw.cms_open_payments_general (physician_npi);
CREATE INDEX IF NOT EXISTS idx_cms_open_payments_general_payer ON hcs_raw.cms_open_payments_general (payer_name);
CREATE INDEX IF NOT EXISTS idx_cms_open_payments_general_year ON hcs_raw.cms_open_payments_general (program_year);

-- hcs_raw.cms_open_payments_research — Open Payments Research Payments
CREATE TABLE IF NOT EXISTS hcs_raw.cms_open_payments_research (
    record_id                   TEXT PRIMARY KEY,
    physician_npi               TEXT,
    payer_name                  TEXT,
    total_amount_of_payment     NUMERIC,
    form_of_payment             TEXT,
    program_year                INTEGER,
    _loaded_at                  TIMESTAMPTZ DEFAULT now(),
    _source_file                TEXT,
    _source_hash                TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_open_payments_research_npi ON hcs_raw.cms_open_payments_research (physician_npi);
CREATE INDEX IF NOT EXISTS idx_cms_open_payments_research_year ON hcs_raw.cms_open_payments_research (program_year);

-- hcs_raw.cms_open_payments_ownership — Open Payments Ownership/Investment
CREATE TABLE IF NOT EXISTS hcs_raw.cms_open_payments_ownership (
    record_id                   TEXT PRIMARY KEY,
    physician_npi               TEXT,
    submitting_manufacturer     TEXT,
    total_amount_invested       NUMERIC,
    value_of_interest           NUMERIC,
    program_year                INTEGER,
    _loaded_at                  TIMESTAMPTZ DEFAULT now(),
    _source_file                TEXT,
    _source_hash                TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_open_payments_ownership_npi ON hcs_raw.cms_open_payments_ownership (physician_npi);

-- hcs_raw.cms_care_compare_physicians — Care Compare Physician Data
CREATE TABLE IF NOT EXISTS hcs_raw.cms_care_compare_physicians (
    npi                         TEXT PRIMARY KEY,
    pac_id                      TEXT,
    professional_enrollment_id  TEXT,
    first_name                  TEXT,
    last_name                   TEXT,
    credential                  TEXT,
    medical_school              TEXT,
    graduation_year             INTEGER,
    primary_specialty           TEXT,
    _loaded_at                  TIMESTAMPTZ DEFAULT now(),
    _source_file                TEXT,
    _source_hash                TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_care_compare_specialty ON hcs_raw.cms_care_compare_physicians (primary_specialty);

-- =============================================================================
-- FACILITY GROUP (10 tables)
-- =============================================================================

-- hcs_raw.cms_pos — Provider of Services
CREATE TABLE IF NOT EXISTS hcs_raw.cms_pos (
    ccn                     TEXT PRIMARY KEY,
    facility_name           TEXT,
    facility_type           TEXT,
    address                 TEXT,
    city                    TEXT,
    state                   TEXT,
    zip_code                TEXT,
    bed_count               INTEGER,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_pos_state ON hcs_raw.cms_pos (state);
CREATE INDEX IF NOT EXISTS idx_cms_pos_type ON hcs_raw.cms_pos (facility_type);

-- hcs_raw.cms_pecos — Provider Enrollment, Chain, and Ownership System
CREATE TABLE IF NOT EXISTS hcs_raw.cms_pecos (
    enrollment_id           TEXT PRIMARY KEY,
    npi                     TEXT,
    org_name                TEXT,
    enrollment_type         TEXT,
    enrollment_state        TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_pecos_npi ON hcs_raw.cms_pecos (npi);

-- hcs_raw.cms_chow — Change of Ownership
CREATE TABLE IF NOT EXISTS hcs_raw.cms_chow (
    chow_id                 TEXT PRIMARY KEY,
    ccn                     TEXT,
    old_owner               TEXT,
    new_owner               TEXT,
    effective_date          DATE,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_chow_ccn ON hcs_raw.cms_chow (ccn);

-- hcs_raw.cms_hospital_affiliation — Hospital Affiliations
CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_affiliation (
    affiliation_id          TEXT PRIMARY KEY,
    npi                     TEXT,
    ccn                     TEXT,
    affiliation_type        TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_hospital_affiliation_npi ON hcs_raw.cms_hospital_affiliation (npi);
CREATE INDEX IF NOT EXISTS idx_cms_hospital_affiliation_ccn ON hcs_raw.cms_hospital_affiliation (ccn);

-- hcs_raw.cms_inpatient_puf — Medicare Inpatient PUF
CREATE TABLE IF NOT EXISTS hcs_raw.cms_inpatient_puf (
    provider_id             TEXT NOT NULL,
    drg_code                TEXT NOT NULL,
    total_discharges        INTEGER,
    avg_covered_charges     NUMERIC,
    avg_total_payments      NUMERIC,
    avg_medicare_payments   NUMERIC,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (provider_id, drg_code, year)
);

CREATE INDEX IF NOT EXISTS idx_cms_inpatient_puf_provider ON hcs_raw.cms_inpatient_puf (provider_id);
CREATE INDEX IF NOT EXISTS idx_cms_inpatient_puf_drg ON hcs_raw.cms_inpatient_puf (drg_code);

-- hcs_raw.cms_outpatient_puf — Medicare Outpatient PUF
CREATE TABLE IF NOT EXISTS hcs_raw.cms_outpatient_puf (
    provider_id             TEXT NOT NULL,
    apc_code                TEXT NOT NULL,
    total_services          INTEGER,
    avg_estimated_payment   NUMERIC,
    avg_total_payments      NUMERIC,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (provider_id, apc_code, year)
);

CREATE INDEX IF NOT EXISTS idx_cms_outpatient_puf_provider ON hcs_raw.cms_outpatient_puf (provider_id);

-- hcs_raw.cms_hospital_quality — Hospital Quality Measures
CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_quality (
    provider_id             TEXT NOT NULL,
    measure_id              TEXT NOT NULL,
    measure_name            TEXT,
    score                   TEXT,
    sample_size             INTEGER,
    footnote                TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (provider_id, measure_id)
);

CREATE INDEX IF NOT EXISTS idx_cms_hospital_quality_measure ON hcs_raw.cms_hospital_quality (measure_id);

-- hcs_raw.cms_hospital_general_info — Hospital General Information
CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_general_info (
    provider_id             TEXT PRIMARY KEY,
    hospital_name           TEXT,
    address                 TEXT,
    city                    TEXT,
    state                   TEXT,
    zip_code                TEXT,
    hospital_type           TEXT,
    ownership               TEXT,
    overall_rating          INTEGER,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_hospital_general_info_state ON hcs_raw.cms_hospital_general_info (state);

-- hcs_raw.cms_hcris — Healthcare Cost Report Information System
CREATE TABLE IF NOT EXISTS hcs_raw.cms_hcris (
    report_id               TEXT PRIMARY KEY,
    provider_ccn            TEXT,
    fiscal_year_begin       DATE,
    fiscal_year_end         DATE,
    total_costs             NUMERIC,
    total_revenue           NUMERIC,
    net_income              NUMERIC,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_hcris_ccn ON hcs_raw.cms_hcris (provider_ccn);

-- hcs_raw.cms_magnet — Magnet Hospital Designations
CREATE TABLE IF NOT EXISTS hcs_raw.cms_magnet (
    facility_id             TEXT PRIMARY KEY,
    facility_name           TEXT,
    city                    TEXT,
    state                   TEXT,
    designation_date        DATE,
    expiration_date         DATE,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_magnet_state ON hcs_raw.cms_magnet (state);

-- =============================================================================
-- DRUG / MARKET GROUP (13 tables)
-- =============================================================================

-- hcs_raw.cms_ndc — National Drug Code Directory
CREATE TABLE IF NOT EXISTS hcs_raw.cms_ndc (
    ndc                     TEXT PRIMARY KEY,
    proprietary_name        TEXT,
    nonproprietary_name     TEXT,
    labeler_name            TEXT,
    dosage_form             TEXT,
    route                   TEXT,
    product_type            TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_ndc_nonproprietary ON hcs_raw.cms_ndc (nonproprietary_name);
CREATE INDEX IF NOT EXISTS idx_cms_ndc_labeler ON hcs_raw.cms_ndc (labeler_name);

-- hcs_raw.cms_part_d_spending — Part D Drug Spending Dashboard
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_spending (
    brand_name              TEXT NOT NULL,
    generic_name            TEXT,
    total_spending           NUMERIC,
    total_claims            INTEGER,
    total_beneficiaries     INTEGER,
    avg_cost_per_claim      NUMERIC,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (brand_name, year)
);

CREATE INDEX IF NOT EXISTS idx_cms_part_d_spending_generic ON hcs_raw.cms_part_d_spending (generic_name);

-- hcs_raw.cms_part_b_spending — Part B Drug Spending Dashboard
CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_b_spending (
    hcpcs_code              TEXT NOT NULL,
    hcpcs_description       TEXT,
    total_spending           NUMERIC,
    total_claims            INTEGER,
    total_beneficiaries     INTEGER,
    avg_cost_per_claim      NUMERIC,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (hcpcs_code, year)
);

-- hcs_raw.cms_formulary — Medicare Part D Formulary Data
CREATE TABLE IF NOT EXISTS hcs_raw.cms_formulary (
    formulary_id            TEXT NOT NULL,
    ndc                     TEXT NOT NULL,
    tier_level              INTEGER,
    prior_authorization     BOOLEAN,
    step_therapy            BOOLEAN,
    quantity_limit          BOOLEAN,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (formulary_id, ndc)
);

CREATE INDEX IF NOT EXISTS idx_cms_formulary_ndc ON hcs_raw.cms_formulary (ndc);

-- hcs_raw.cms_rbcs — Restructured BETOS Classification System
CREATE TABLE IF NOT EXISTS hcs_raw.cms_rbcs (
    hcpcs_code              TEXT PRIMARY KEY,
    rbcs_id                 TEXT,
    rbcs_category           TEXT,
    rbcs_subcategory        TEXT,
    rbcs_family             TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

-- hcs_raw.cms_usp — US Pharmacopeia Drug Classifications
CREATE TABLE IF NOT EXISTS hcs_raw.cms_usp (
    usp_category            TEXT NOT NULL,
    usp_class               TEXT NOT NULL,
    drug_name               TEXT,
    ndc                     TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (usp_category, usp_class)
);

-- hcs_raw.cms_nucc — National Uniform Claim Committee Taxonomy
CREATE TABLE IF NOT EXISTS hcs_raw.cms_nucc (
    taxonomy_code           TEXT PRIMARY KEY,
    provider_type           TEXT,
    classification          TEXT,
    specialization          TEXT,
    grouping_name           TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

-- hcs_raw.cms_geographic_variation — Geographic Variation PUF
CREATE TABLE IF NOT EXISTS hcs_raw.cms_geographic_variation (
    state                   TEXT NOT NULL,
    county                  TEXT NOT NULL,
    bene_count              INTEGER,
    total_actual_costs      NUMERIC,
    per_capita_costs        NUMERIC,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (state, county, year)
);

CREATE INDEX IF NOT EXISTS idx_cms_geographic_variation_state ON hcs_raw.cms_geographic_variation (state);

-- hcs_raw.cms_chronic_conditions — Chronic Conditions PUF
CREATE TABLE IF NOT EXISTS hcs_raw.cms_chronic_conditions (
    state                   TEXT NOT NULL,
    condition               TEXT NOT NULL,
    prevalence_rate         NUMERIC,
    bene_count              INTEGER,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (state, condition, year)
);

-- hcs_raw.cms_post_acute — Post-Acute Care PUF
CREATE TABLE IF NOT EXISTS hcs_raw.cms_post_acute (
    provider_id             TEXT NOT NULL,
    provider_type           TEXT,
    total_episodes          INTEGER,
    avg_spending_per_episode NUMERIC,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (provider_id, year)
);

-- hcs_raw.cms_dmepos — Durable Medical Equipment, Prosthetics, Orthotics, and Supplies
CREATE TABLE IF NOT EXISTS hcs_raw.cms_dmepos (
    npi                     TEXT NOT NULL,
    hcpcs_code              TEXT NOT NULL,
    total_services          INTEGER,
    total_beneficiaries     INTEGER,
    avg_submitted_charge    NUMERIC,
    avg_medicare_payment    NUMERIC,
    year                    INTEGER NOT NULL,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (npi, hcpcs_code, year)
);

CREATE INDEX IF NOT EXISTS idx_cms_dmepos_hcpcs ON hcs_raw.cms_dmepos (hcpcs_code);

-- hcs_raw.cms_ddinter — Drug-Drug Interactions Reference
CREATE TABLE IF NOT EXISTS hcs_raw.cms_ddinter (
    drug_a                  TEXT NOT NULL,
    drug_b                  TEXT NOT NULL,
    interaction_level       TEXT,
    description             TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (drug_a, drug_b)
);

-- hcs_raw.cms_stabilis — IV Drug Stability/Compatibility Reference
CREATE TABLE IF NOT EXISTS hcs_raw.cms_stabilis (
    drug_name               TEXT NOT NULL,
    route                   TEXT NOT NULL,
    diluent                 TEXT,
    stability_hours         NUMERIC,
    storage_condition       TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (drug_name, route)
);

COMMIT;

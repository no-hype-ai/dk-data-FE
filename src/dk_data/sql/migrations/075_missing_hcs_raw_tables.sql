-- Migration 075: Backfill missing hcs_raw tables and ON CONFLICT indexes (issue #203)
--
-- Context:
-- - Some environments were baselined after older migrations and missed hcs_raw table creation.
-- - Several loaders use ON CONFLICT keys that require explicit unique indexes.
--
-- This migration is intended to be idempotent.

CREATE SCHEMA IF NOT EXISTS hcs_raw;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_home_health (
  id BIGSERIAL PRIMARY KEY,
  cms_certification_number TEXT,
  provider_name TEXT,
  address TEXT,
  city TEXT,
  state TEXT,
  zip_code TEXT,
  phone_number TEXT,
  type_of_ownership TEXT,
  offers_nursing_care TEXT,
  offers_physical_therapy TEXT,
  offers_occupational_therapy TEXT,
  offers_speech_pathology TEXT,
  offers_medical_social TEXT,
  offers_home_health_aide TEXT,
  quality_of_patient_care_star_rating TEXT,
  how_often_the_home_health_team_began_their_patients_care_timely TEXT,
  data_collection_period_start_date TEXT,
  data_collection_period_end_date TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hcs_raw_cms_home_health_ccn
  ON hcs_raw.cms_home_health(cms_certification_number)
  WHERE cms_certification_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospice_puf (
  id BIGSERIAL PRIMARY KEY,
  cms_certification_number TEXT,
  facility_name TEXT,
  address TEXT,
  city TEXT,
  state TEXT,
  zip_code TEXT,
  phone_number TEXT,
  type_of_ownership TEXT,
  facility_type TEXT,
  medicare_enrollment_date TEXT,
  quality_care_score TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hcs_raw_cms_hospice_puf_ccn
  ON hcs_raw.cms_hospice_puf(cms_certification_number)
  WHERE cms_certification_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_snf_puf (
  id BIGSERIAL PRIMARY KEY,
  cms_certification_number TEXT,
  provider_name TEXT,
  address TEXT,
  city TEXT,
  state TEXT,
  zip_code TEXT,
  phone_number TEXT,
  county_name TEXT,
  ownership_type TEXT,
  number_of_certified_beds TEXT,
  overall_rating TEXT,
  health_inspection_rating TEXT,
  qm_rating TEXT,
  long_stay_qm_rating TEXT,
  short_stay_qm_rating TEXT,
  staffing_rating TEXT,
  rn_staffing_rating TEXT,
  processing_date TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hcs_raw_cms_snf_puf_ccn
  ON hcs_raw.cms_snf_puf(cms_certification_number)
  WHERE cms_certification_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_dme_puf (
  id BIGSERIAL PRIMARY KEY,
  npi TEXT,
  nppes_provider_last_org_name TEXT,
  nppes_provider_first_name TEXT,
  nppes_provider_mi TEXT,
  nppes_credentials TEXT,
  nppes_provider_gender TEXT,
  nppes_entity_code TEXT,
  nppes_provider_street1 TEXT,
  nppes_provider_street2 TEXT,
  nppes_provider_city TEXT,
  nppes_provider_zip TEXT,
  nppes_provider_state TEXT,
  nppes_provider_country TEXT,
  provider_type TEXT,
  medicare_participation_indicator TEXT,
  place_of_service TEXT,
  hcpcs_code TEXT,
  hcpcs_description TEXT,
  bene_count TEXT,
  total_submitted_chrg_amt TEXT,
  total_medicare_allowed_amt TEXT,
  total_medicare_payment_amt TEXT,
  total_medicare_stnd_amt TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hcs_raw_cms_dme_puf_npi_hcpcs
  ON hcs_raw.cms_dme_puf(npi, hcpcs_code)
  WHERE npi IS NOT NULL AND hcpcs_code IS NOT NULL;

-- Missing ON CONFLICT unique indexes ----------------------------------------

-- Derived from src/dk_data/ingestion/sources/cms_inpatient.py ON CONFLICT key,
-- applied to hcs_raw.cms_inpatient_puf.
DO $$
BEGIN
  IF to_regclass('hcs_raw.cms_inpatient_puf') IS NOT NULL THEN
    EXECUTE '
      CREATE UNIQUE INDEX IF NOT EXISTS uq_hcs_raw_cms_inpatient_puf_conflict
      ON hcs_raw.cms_inpatient_puf(provider_id, fiscal_year, drg_code)
    ';
  ELSE
    RAISE NOTICE 'Table hcs_raw.cms_inpatient_puf missing; skipped uq_hcs_raw_cms_inpatient_puf_conflict';
  END IF;
END $$;

-- TODO(issue-203): Verify these conflict keys against the canonical loaders.
-- Using natural keys because no matching loader file was found in src/dk_data/ingestion/sources.
DO $$
BEGIN
  IF to_regclass('hcs_raw.cms_medicaid_drug_spending') IS NOT NULL THEN
    EXECUTE '
      CREATE UNIQUE INDEX IF NOT EXISTS uq_hcs_raw_cms_medicaid_drug_spending_conflict
      ON hcs_raw.cms_medicaid_drug_spending(drug_name, year)
    ';
  ELSE
    RAISE NOTICE 'Table hcs_raw.cms_medicaid_drug_spending missing; skipped uq_hcs_raw_cms_medicaid_drug_spending_conflict';
  END IF;
END $$;

-- TODO(issue-203): Verify these conflict keys against the canonical loaders.
-- Using natural keys because no matching loader file was found in src/dk_data/ingestion/sources.
DO $$
BEGIN
  IF to_regclass('hcs_raw.cms_medicare_advantage') IS NOT NULL THEN
    EXECUTE '
      CREATE UNIQUE INDEX IF NOT EXISTS uq_hcs_raw_cms_medicare_advantage_conflict
      ON hcs_raw.cms_medicare_advantage(organization_name, plan_type, year)
    ';
  ELSE
    RAISE NOTICE 'Table hcs_raw.cms_medicare_advantage missing; skipped uq_hcs_raw_cms_medicare_advantage_conflict';
  END IF;
END $$;

-- Derived from src/dk_data/data/load_openfda_labels.py ON CONFLICT (spl_id).
DO $$
BEGIN
  IF to_regclass('bronze.openfda_labels') IS NOT NULL THEN
    EXECUTE '
      CREATE UNIQUE INDEX IF NOT EXISTS uq_openfda_labels_conflict
      ON bronze.openfda_labels(spl_id)
    ';
  ELSE
    RAISE NOTICE 'Table bronze.openfda_labels missing; skipped uq_openfda_labels_conflict';
  END IF;
END $$;

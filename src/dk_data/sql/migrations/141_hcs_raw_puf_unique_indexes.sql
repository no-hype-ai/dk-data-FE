-- Migration 141: Add missing unique indexes for hcs_raw PUF tables
-- Required by ON CONFLICT clauses in their loaders (upsert_records).
-- Without these, any upsert on these tables crashes with:
--   "there is no unique or exclusion constraint matching the ON CONFLICT specification"

-- cms_claim_type_puf: conflict_columns=['bene_geo_lvl', 'clm_type', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_claim_type_puf_key
    ON hcs_raw.cms_claim_type_puf (bene_geo_lvl, clm_type, _source_year);

-- cms_enrollment_puf: conflict_columns=['state_cd', 'county_cd', 'bene_demo_lvl', 'bene_age_lvl', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_enrollment_puf_key
    ON hcs_raw.cms_enrollment_puf (state_cd, county_cd, bene_demo_lvl, bene_age_lvl, _source_year);

-- cms_inpatient_puf: conflict_columns=['_source_hash', 'provider_id']
-- (drg_definition can be NULL for provider-level records; 2-column key is used as surrogate)
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_inpatient_puf_key
    ON hcs_raw.cms_inpatient_puf (_source_hash, provider_id);

-- cms_medicaid_drug_spending: conflict_columns=['gnrc_name', 'util_type', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_medicaid_drug_spending_key
    ON hcs_raw.cms_medicaid_drug_spending (gnrc_name, util_type, _source_year);

-- cms_medicare_advantage: conflict_columns=['_source_hash', 'enrollment_data_period', 'fips_cd']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_medicare_advantage_key
    ON hcs_raw.cms_medicare_advantage (_source_hash, enrollment_data_period, fips_cd);

-- cms_mental_health_puf: conflict_columns=['npi', 'hcpcs_cd', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_mental_health_puf_key
    ON hcs_raw.cms_mental_health_puf (npi, hcpcs_cd, _source_year);

-- cms_opioid_puf: conflict_columns=['_source_hash', 'prscrbr_npi', 'gnrc_name', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_opioid_puf_key
    ON hcs_raw.cms_opioid_puf (_source_hash, prscrbr_npi, gnrc_name, _source_year);

-- cms_ordering_providers: conflict_columns=['rndrng_npi', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_ordering_providers_key
    ON hcs_raw.cms_ordering_providers (rndrng_npi, _source_year);

-- cms_referring_providers: conflict_columns=['rndrng_npi', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_referring_providers_key
    ON hcs_raw.cms_referring_providers (rndrng_npi, _source_year);

-- cms_telehealth_puf: conflict_columns=['npi', 'hcpcs_cd', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_telehealth_puf_key
    ON hcs_raw.cms_telehealth_puf (npi, hcpcs_cd, _source_year);

-- cms_utilization_puf: conflict_columns=['bene_geo_cd', 'bene_demo_lvl', '_source_year']
CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_utilization_puf_key
    ON hcs_raw.cms_utilization_puf (bene_geo_cd, bene_demo_lvl, _source_year);

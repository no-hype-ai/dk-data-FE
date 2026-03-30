-- Migration 124: Register all data sources missing from meta.data_sources
-- Adds the 55 sources defined in ingestion/main.py that were never seeded:
--   - 47 CMS PUF / facility / reference sources (added in branches 016–019)
--   - 8 additional sources: clinicaltrials, openfda_labels, europepmc,
--     euipo_designs, nih_reporter, hrsa, who_icd, who_inn

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES

    -- ── CMS PUF data files ──────────────────────────────────────────────────

    ('cms_chronic_conditions', 'api',
     'https://data.cms.gov/medicare-chronic-conditions/multiple-chronic-conditions',
     'CMS Medicare multiple chronic conditions prevalence and utilization by beneficiary demographics',
     'annual', TRUE),

    ('cms_claim_type_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare claim-type utilization PUF with service counts and payments by claim category',
     'annual', TRUE),

    ('cms_cost_reports_puf', 'csv',
     'https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports',
     'CMS Hospital Cost Report (HCRIS) PUF with facility-level financial and utilization statistics',
     'annual', TRUE),

    ('cms_cost_reports_puf_lines', 'csv',
     'https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports',
     'CMS Hospital Cost Report line-level detail records from HCRIS PUF',
     'annual', TRUE),

    ('cms_dme_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Durable Medical Equipment (DME) PUF with supplier-level utilization and payment data',
     'annual', TRUE),

    ('cms_dual_eligible', 'api',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare-Medicaid dual eligible beneficiary statistics by state and demographic group',
     'annual', TRUE),

    ('cms_enrollment_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare enrollment PUF with beneficiary counts by plan type, geography, and demographics',
     'monthly', TRUE),

    ('cms_geographic_variation', 'csv',
     'https://www.cms.gov/Research-Statistics-Data-and-Systems/Statistics-Trends-and-Reports/Medicare-Geographic-Variation',
     'CMS Medicare Geographic Variation PUF with per-capita spending and utilization by geography',
     'annual', TRUE),

    ('cms_home_health', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Home Health Agency PUF with agency-level utilization, quality, and payment data',
     'annual', TRUE),

    ('cms_hospice_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Hospice PUF with provider-level utilization, diagnoses, and Medicare payment data',
     'annual', TRUE),

    ('cms_imaging_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare imaging services PUF with utilization and standardized payments by procedure',
     'annual', TRUE),

    ('cms_inpatient_puf', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals',
     'CMS Medicare Inpatient Hospital PUF with DRG-level discharge and payment summaries',
     'annual', TRUE),

    ('cms_lab_services', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare lab services PUF with HCPCS-level utilization and payments for clinical laboratory',
     'annual', TRUE),

    ('cms_medicaid_drug_spending', 'api',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicaid drug spending by NDC with unit costs and total expenditures by state',
     'annual', TRUE),

    ('cms_medicare_advantage', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Advantage enrollment and plan landscape data with premiums and benefits',
     'monthly', TRUE),

    ('cms_mental_health_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare mental health utilization PUF with service-level utilization and spending',
     'annual', TRUE),

    ('cms_nppes', 'csv',
     'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
     'CMS National Plan and Provider Enumeration System (NPPES) NPI provider registry',
     'monthly', TRUE),

    ('cms_open_payments', 'api',
     'https://data.cms.gov/provider-data',
     'CMS Open Payments (Sunshine Act) financial relationships between industry and physicians',
     'annual', TRUE),

    ('cms_opioid_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare opioid prescribing PUF with prescriber-level opioid utilization metrics',
     'annual', TRUE),

    ('cms_ordering_providers', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare ordering and referring providers utilization and payment summary',
     'annual', TRUE),

    ('cms_outpatient_puf', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Outpatient Hospital PUF with APC-level utilization and payment summaries',
     'annual', TRUE),

    ('cms_part_b_spending', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Part B drug spending by HCPCS with dosage units and average sales price',
     'annual', TRUE),

    ('cms_part_d_prescriber', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Part D prescriber PUF with drug-level prescribing counts and costs by provider',
     'annual', TRUE),

    ('cms_part_d_spending', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Part D drug spending PUF with per-unit costs and annual expenditures',
     'annual', TRUE),

    ('cms_physician_puf', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Physician and Other Practitioners PUF with HCPCS-level service utilization',
     'annual', TRUE),

    ('cms_physician_puf_services', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Physician PUF service-level detail with allowed amounts and place of service',
     'annual', TRUE),

    ('cms_referring_providers', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare referring providers utilization and payment summary by specialty',
     'annual', TRUE),

    ('cms_snf_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Skilled Nursing Facility (SNF) PUF with facility-level utilization and payment data',
     'annual', TRUE),

    ('cms_telehealth_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare telehealth utilization PUF with service counts and spending by provider',
     'annual', TRUE),

    ('cms_utilization_puf', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare utilization PUF aggregating service-level utilization and payment across claim types',
     'annual', TRUE),

    -- ── CMS facility / provider / reference sources ─────────────────────────

    ('cms_care_compare', 'api',
     'https://data.cms.gov/provider-data',
     'CMS Care Compare facility data including hospitals, nursing homes, home health, hospice',
     'monthly', TRUE),

    ('cms_chow', 'api',
     'https://data.cms.gov/provider-data',
     'CMS Change of Ownership (CHOW) records for Medicare-certified facilities',
     'monthly', TRUE),

    ('cms_ddinter', 'api',
     'https://ddinter.scbdd.com',
     'Drug-drug interaction (DDInter) database with interaction severity classifications',
     'monthly', TRUE),

    ('cms_dmepos', 'api',
     'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
     'CMS DMEPOS supplier enrollment and accreditation data',
     'monthly', TRUE),

    ('cms_formulary', 'csv',
     'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Part D formulary data with tier classifications and utilization management',
     'monthly', TRUE),

    ('cms_hcris', 'csv',
     'https://downloads.cms.gov/files/hcris',
     'CMS Healthcare Cost Report Information System (HCRIS) raw report files',
     'annual', TRUE),

    ('cms_hospital_affiliation', 'api',
     'https://data.cms.gov/provider-data',
     'CMS hospital-physician affiliation data linking providers to facilities',
     'monthly', TRUE),

    ('cms_hospital_general_info', 'api',
     'https://data.cms.gov/provider-data/dataset/xubh-q36u',
     'CMS Hospital General Information including demographics, ownership, and overall quality star rating',
     'monthly', TRUE),

    ('cms_hospital_quality', 'api',
     'https://data.cms.gov/provider-data',
     'CMS Hospital Quality measures including HCAHPS, readmissions, mortality, and safety scores',
     'monthly', TRUE),

    ('cms_inpatient', 'csv',
     'https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals',
     'CMS Medicare Inpatient data with TAVR procedure volumes by DRG code',
     'quarterly', TRUE),

    ('cms_magnet', 'api',
     'https://www.nursingworld.org/organizational-programs/magnet',
     'ANCC Magnet Recognition and Pathway to Excellence hospital designations',
     'monthly', TRUE),

    ('cms_ndc', 'api',
     'https://open.fda.gov/apis/drug/ndc',
     'FDA National Drug Code (NDC) directory via openFDA for drug product identification',
     'weekly', TRUE),

    ('cms_nucc', 'csv',
     'https://nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40',
     'NUCC Health Care Provider Taxonomy code set for provider classification',
     'monthly', TRUE),

    ('cms_pecos', 'api',
     'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
     'CMS PECOS Medicare provider enrollment and specialty data',
     'monthly', TRUE),

    ('cms_pos', 'api',
     'https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-hospital-non-hospital-facilities',
     'CMS Provider of Services file for hospital and non-hospital facility characteristics',
     'monthly', TRUE),

    ('cms_post_acute', 'api',
     'https://data.cms.gov/provider-data',
     'CMS post-acute care quality data for SNF, HHA, IRF, and LTCH providers',
     'monthly', TRUE),

    ('cms_rbcs', 'api',
     'https://data.cms.gov/provider-summary-by-type-of-service/provider-service-classifications',
     'CMS Restructured BETOS Classification System procedure code categorization',
     'annual', TRUE),

    ('cms_stabilis', 'api',
     'https://www.stabilis.org',
     'Stabilis drug physicochemical stability database for IV drug compatibility',
     'monthly', TRUE),

    ('cms_usp', 'api',
     'https://www.usp.org/health-quality-safety/usp-medicare-model-guidelines',
     'USP Medicare Model Guidelines for therapeutic classification of Part D drug plans',
     'annual', TRUE),

    -- ── Additional ingestion pipeline sources ───────────────────────────────

    ('clinicaltrials', 'api',
     'https://clinicaltrials.gov/api/v2/studies',
     'ClinicalTrials.gov v2 API study records with eligibility, status, and trial design',
     'weekly', TRUE),

    ('openfda_labels', 'api',
     'https://api.fda.gov/drug/label.json',
     'FDA openFDA drug label (SPL) records with indications, warnings, and dosage information',
     'weekly', TRUE),

    ('europepmc', 'api',
     'https://www.ebi.ac.uk/europepmc/webservices/rest',
     'Europe PMC literature search for pharmaceutical and clinical research publications',
     'daily', TRUE),

    ('euipo_designs', 'api',
     'https://api.euipo.europa.eu/design-search/designs',
     'EUIPO registered industrial design search for pharmaceutical packaging and device designs',
     'weekly', TRUE),

    ('nih_reporter', 'api',
     'https://api.reporter.nih.gov/v2/projects/search',
     'NIH Research Portfolio Online Reporting Tools (RePORTER) funded research project grants',
     'weekly', TRUE),

    ('hrsa', 'api',
     'https://data.hrsa.gov',
     'HRSA Health Resources and Services Administration data including shortage areas and provider data',
     'monthly', TRUE),

    ('who_icd', 'api',
     'https://id.who.int/icd/release/11/2024-01/mms',
     'WHO ICD-10 and ICD-11 disease classification codes for diagnosis standardisation',
     'annual', TRUE),

    ('who_inn', 'api',
     'https://www.who.int/teams/health-product-and-policy-standards/inn',
     'WHO International Nonproprietary Names (INN) for pharmaceutical substances',
     'monthly', TRUE)

ON CONFLICT (source_name) DO UPDATE SET
    source_url        = EXCLUDED.source_url,
    description       = EXCLUDED.description,
    refresh_frequency = EXCLUDED.refresh_frequency,
    is_active         = EXCLUDED.is_active;

DO $$
BEGIN
    RAISE NOTICE 'Migration 124: % data sources upserted into meta.data_sources',
        (SELECT COUNT(*) FROM meta.data_sources);
END
$$;

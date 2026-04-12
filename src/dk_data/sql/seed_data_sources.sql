-- Seed data for meta.data_sources
-- Initial configuration of data sources for the TAVR platform

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES
    ('cms_medicare_inpatient', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals',
     'CMS Medicare Inpatient data with TAVR procedure volumes by DRG code', 'quarterly', TRUE),

    ('cms_hospital_info', 'csv', 'https://data.cms.gov/provider-data/dataset/xubh-q36u',
     'CMS Hospital General Information including demographics, ownership, and quality ratings', 'monthly', TRUE),

    ('cms_cost_reports', 'csv', 'https://data.cms.gov/provider-compliance/cost-report',
     'CMS Hospital Cost Reports (HCRIS) with financial metrics', 'annual', TRUE),

    ('acc_tvc', 'csv', 'https://services.ncdr.com/PublicReportingApiV2/DataDownload/TVTMetrics',
     'ACC Transcatheter Valve Certification and TVT Registry data via NCDR Public Reporting API', 'quarterly', TRUE),

    ('hrsa_shortage_areas', 'api', 'https://data.hrsa.gov/api',
     'HRSA Health Professional Shortage Area (HPSA) designations', 'monthly', TRUE),

    ('bindingdb', 'api', 'https://www.bindingdb.org/bind/downloads',
     'BindingDB binding affinity data for drug-target interactions', 'monthly', TRUE),

    ('orange_book', 'csv', 'https://www.fda.gov/drugs/drug-approvals-and-databases/approved-drug-products-therapeutically-equivalent-evaluations-orange-book',
     'FDA Orange Book approved drug products with patent and exclusivity data', 'weekly', TRUE),

    ('sider', 'csv', 'http://sideeffects.embl.de',
     'SIDER side effect database linking drugs to adverse drug reactions', 'monthly', TRUE),

    ('tdc_admet', 'api', 'https://tdcommons.ai',
     'Therapeutics Data Commons ADMET property predictions for drug compounds', 'monthly', TRUE),

    ('ema', 'api', 'https://www.ema.europa.eu/en/medicines',
     'European Medicines Agency approved medicines and regulatory decisions', 'weekly', TRUE),

    ('rxnorm', 'api', 'https://rxnav.nlm.nih.gov/REST',
     'NLM RxNorm drug nomenclature and normalized drug names', 'weekly', TRUE),

    ('dailymed', 'api', 'https://dailymed.nlm.nih.gov/dailymed/services',
     'NLM DailyMed structured product labeling and drug label data', 'weekly', TRUE),

    ('fda_drugs', 'api', 'https://api.fda.gov/drug/drugsfda.json',
     'FDA Drugs@FDA database of approved drug products with regulatory actions', 'weekly', TRUE),

    ('kegg_drug', 'api', 'https://rest.kegg.jp',
     'KEGG Drug database linking drugs to pathways, targets, and disease associations', 'monthly', TRUE),

    ('ttd', 'api', 'https://db.idrblab.net/ttd',
     'Therapeutic Target Database linking targets to drugs and diseases', 'monthly', TRUE),

    ('pharmgkb', 'api', 'https://api.pharmgkb.org/v1',
     'PharmGKB pharmacogenomics knowledge base with drug-gene-disease relationships', 'monthly', TRUE),

    ('imgt', 'api', 'https://www.imgt.org/IMGT_vquest',
     'ImMunoGeneTics information system for antibody and biologic sequence data', 'monthly', TRUE),

    ('cdc_vaccines', 'api', 'https://data.cdc.gov/resource',
     'CDC vaccine information including schedules, coverage, and safety monitoring data', 'monthly', TRUE),

    -- CI sources (011-datasource-integration)
    ('pubmed', 'api', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils',
     'PubMed literature via NCBI E-utilities for pharmaceutical competitive intelligence', 'daily', TRUE),

    ('openalex_ci', 'api', 'https://api.openalex.org/works',
     'OpenAlex pharmaceutical research works for competitive intelligence monitoring', 'daily', TRUE),

    ('ema_regulatory', 'api', 'https://www.ema.europa.eu/en/medicines',
     'EMA regulatory decisions including CHMP opinions, EPARs, and safety signals', 'weekly', TRUE),

    -- Credential-gated CI sources (US4)
    ('drugbank', 'api', 'https://go.drugbank.com/releases/latest',
     'DrugBank drug data with targets, enzymes, and pharmacology (credential-gated)', 'monthly', TRUE),

    ('uspto_patents', 'api', 'https://search.patentsview.org/api/v1/patent/',
     'USPTO PatentSearch pharmaceutical patents with CPC code filtering', 'weekly', TRUE),

    -- Medium-impact CI sources (US5)
    ('journal_rss', 'rss', 'https://www.nejm.org/action/showFeed',
     'Journal RSS feeds from NEJM, Lancet, JAMA, BMJ, Nature Medicine', 'daily', TRUE),

    ('uspto_ci', 'api', 'https://search.patentsview.org/api/v1/patent/',
     'USPTO PatentSearch CI pharma patents with query-scoped search terms', 'weekly', TRUE),

    ('hta_bodies', 'api', 'https://www.nice.org.uk/guidance/published',
     'HTA body decisions from NICE, G-BA, HAS, and PBAC', 'weekly', TRUE),

    -- Lower-impact CI sources (US6)
    ('epo_ops', 'api', 'https://ops.epo.org/3.2/rest-services/',
     'EPO Open Patent Services pharma patents (credential-gated)', 'weekly', TRUE),

    ('cochrane', 'api', 'https://www.cochranelibrary.com/cdsr/reviews',
     'Cochrane Library systematic reviews for pharmaceutical interventions', 'monthly', TRUE),

    ('medical_news', 'rss', 'https://www.medscape.com/rss',
     'Medical news from Medscape, Healio, and FiercePharma RSS feeds', 'daily', TRUE),

    ('sec_edgar', 'api', 'https://efts.sec.gov/LATEST/search-index',
     'SEC EDGAR pharmaceutical company filings (10-K, 10-Q, 8-K)', 'daily', TRUE),

    -- Molecule data sources (012-platform-hardening)
    ('uniprot', 'api', 'https://rest.uniprot.org/uniprotkb',
     'UniProt protein database for drug target identification and annotation', 'weekly', TRUE),

    ('pdb', 'api', 'https://data.rcsb.org/rest/v1',
     'RCSB Protein Data Bank for 3D protein structure data', 'weekly', TRUE),

    ('orcid', 'api', 'https://pub.orcid.org/v3.0',
     'ORCID researcher profiles for key opinion leader identification', 'weekly', TRUE),

    -- Trademark data sources (014-uspto-euipo-model-datasource)
    ('uspto_trademarks', 'api', 'https://tsdrapi.uspto.gov/',
     'USPTO TSDR trademark case status data for pharmaceutical trademarks (Nice Class 5)', 'weekly', TRUE),

    ('euipo_trademarks', 'api', 'https://www.tmdn.org/tmview/api/search',
     'EUIPO trademark data via TMview federated search for pharmaceutical trademarks (Nice Class 5)', 'weekly', TRUE),

    -- CMS PUF data files (016–019)
    ('cms_chronic_conditions', 'api', 'https://data.cms.gov/medicare-chronic-conditions/multiple-chronic-conditions',
     'CMS Medicare multiple chronic conditions prevalence and utilization by beneficiary demographics', 'annual', TRUE),
    ('cms_claim_type_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare claim-type utilization PUF with service counts and payments by claim category', 'annual', TRUE),
    ('cms_cost_reports_puf', 'csv', 'https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports',
     'CMS Hospital Cost Report (HCRIS) PUF with facility-level financial and utilization statistics', 'annual', TRUE),
    ('cms_cost_reports_puf_lines', 'csv', 'https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports',
     'CMS Hospital Cost Report line-level detail records from HCRIS PUF', 'annual', TRUE),
    ('cms_dme_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Durable Medical Equipment (DME) PUF with supplier-level utilization and payment data', 'annual', TRUE),
    ('cms_dual_eligible', 'api', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare-Medicaid dual eligible beneficiary statistics by state and demographic group', 'annual', TRUE),
    ('cms_enrollment_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare enrollment PUF with beneficiary counts by plan type, geography, and demographics', 'monthly', TRUE),
    ('cms_geographic_variation', 'csv', 'https://www.cms.gov/Research-Statistics-Data-and-Systems/Statistics-Trends-and-Reports/Medicare-Geographic-Variation',
     'CMS Medicare Geographic Variation PUF with per-capita spending and utilization by geography', 'annual', TRUE),
    ('cms_home_health', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Home Health Agency PUF with agency-level utilization, quality, and payment data', 'annual', TRUE),
    ('cms_hospice_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Hospice PUF with provider-level utilization, diagnoses, and Medicare payment data', 'annual', TRUE),
    ('cms_imaging_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare imaging services PUF with utilization and standardized payments by procedure', 'annual', TRUE),
    ('cms_inpatient_puf', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals',
     'CMS Medicare Inpatient Hospital PUF with DRG-level discharge and payment summaries', 'annual', TRUE),
    ('cms_lab_services', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare lab services PUF with HCPCS-level utilization and payments for clinical laboratory', 'annual', TRUE),
    ('cms_medicaid_drug_spending', 'api', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicaid drug spending by NDC with unit costs and total expenditures by state', 'annual', TRUE),
    ('cms_medicare_advantage', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Advantage enrollment and plan landscape data with premiums and benefits', 'monthly', TRUE),
    ('cms_mental_health_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare mental health utilization PUF with service-level utilization and spending', 'annual', TRUE),
    ('cms_nppes', 'csv', 'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
     'CMS National Plan and Provider Enumeration System (NPPES) NPI provider registry', 'monthly', TRUE),
    ('cms_open_payments', 'api', 'https://data.cms.gov/provider-data',
     'CMS Open Payments (Sunshine Act) financial relationships between industry and physicians', 'annual', TRUE),
    ('cms_opioid_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare opioid prescribing PUF with prescriber-level opioid utilization metrics', 'annual', TRUE),
    ('cms_ordering_providers', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare ordering and referring providers utilization and payment summary', 'annual', TRUE),
    ('cms_outpatient_puf', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Outpatient Hospital PUF with APC-level utilization and payment summaries', 'annual', TRUE),
    ('cms_part_b_spending', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Part B drug spending by HCPCS with dosage units and average sales price', 'annual', TRUE),
    ('cms_part_d_prescriber', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Part D prescriber PUF with drug-level prescribing counts and costs by provider', 'annual', TRUE),
    ('cms_part_d_spending', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Part D drug spending PUF with per-unit costs and annual expenditures', 'annual', TRUE),
    ('cms_physician_puf', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Physician and Other Practitioners PUF with HCPCS-level service utilization', 'annual', TRUE),
    ('cms_physician_puf_services', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare Physician PUF service-level detail with allowed amounts and place of service', 'annual', TRUE),
    ('cms_referring_providers', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service',
     'CMS Medicare referring providers utilization and payment summary by specialty', 'annual', TRUE),
    ('cms_snf_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Skilled Nursing Facility (SNF) PUF with facility-level utilization and payment data', 'annual', TRUE),
    ('cms_telehealth_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare telehealth utilization PUF with service counts and spending by provider', 'annual', TRUE),
    ('cms_utilization_puf', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare utilization PUF aggregating service-level utilization and payment across claim types', 'annual', TRUE),

    -- CMS facility / provider / reference sources (016–019)
    ('cms_care_compare', 'api', 'https://data.cms.gov/provider-data',
     'CMS Care Compare facility data including hospitals, nursing homes, home health, hospice', 'monthly', TRUE),
    ('cms_chow', 'api', 'https://data.cms.gov/provider-data',
     'CMS Change of Ownership (CHOW) records for Medicare-certified facilities', 'monthly', TRUE),
    ('cms_ddinter', 'api', 'https://ddinter.scbdd.com',
     'Drug-drug interaction (DDInter) database with interaction severity classifications', 'monthly', TRUE),
    ('cms_dmepos', 'api', 'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
     'CMS DMEPOS supplier enrollment and accreditation data', 'monthly', TRUE),
    ('cms_formulary', 'csv', 'https://data.cms.gov/data-api/v1/dataset',
     'CMS Medicare Part D formulary data with tier classifications and utilization management', 'monthly', TRUE),
    ('cms_hcris', 'csv', 'https://downloads.cms.gov/files/hcris',
     'CMS Healthcare Cost Report Information System (HCRIS) raw report files', 'annual', TRUE),
    ('cms_hospital_affiliation', 'api', 'https://data.cms.gov/provider-data',
     'CMS hospital-physician affiliation data linking providers to facilities', 'monthly', TRUE),
    ('cms_hospital_general_info', 'api', 'https://data.cms.gov/provider-data/dataset/xubh-q36u',
     'CMS Hospital General Information including demographics, ownership, and overall quality star rating', 'monthly', TRUE),
    ('cms_hospital_quality', 'api', 'https://data.cms.gov/provider-data',
     'CMS Hospital Quality measures including HCAHPS, readmissions, mortality, and safety scores', 'monthly', TRUE),
    ('cms_inpatient', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals',
     'CMS Medicare Inpatient data with TAVR procedure volumes by DRG code', 'quarterly', TRUE),
    ('cms_magnet', 'api', 'https://www.nursingworld.org/organizational-programs/magnet',
     'ANCC Magnet Recognition and Pathway to Excellence hospital designations', 'monthly', TRUE),
    ('cms_ndc', 'api', 'https://open.fda.gov/apis/drug/ndc',
     'FDA National Drug Code (NDC) directory via openFDA for drug product identification', 'weekly', TRUE),
    ('cms_nucc', 'csv', 'https://nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40',
     'NUCC Health Care Provider Taxonomy code set for provider classification', 'monthly', TRUE),
    ('cms_pecos', 'api', 'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
     'CMS PECOS Medicare provider enrollment and specialty data', 'monthly', TRUE),
    ('cms_pos', 'api', 'https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-hospital-non-hospital-facilities',
     'CMS Provider of Services file for hospital and non-hospital facility characteristics', 'monthly', TRUE),
    ('cms_post_acute', 'api', 'https://data.cms.gov/provider-data',
     'CMS post-acute care quality data for SNF, HHA, IRF, and LTCH providers', 'monthly', TRUE),
    ('cms_rbcs', 'api', 'https://data.cms.gov/provider-summary-by-type-of-service/provider-service-classifications',
     'CMS Restructured BETOS Classification System procedure code categorization', 'annual', TRUE),
    ('cms_stabilis', 'api', 'https://www.stabilis.org',
     'Stabilis drug physicochemical stability database for IV drug compatibility', 'monthly', TRUE),
    ('cms_usp', 'api', 'https://www.usp.org/health-quality-safety/usp-medicare-model-guidelines',
     'USP Medicare Model Guidelines for therapeutic classification of Part D drug plans', 'annual', TRUE),

    -- Additional pipeline sources (019-cms-puf-platform-reconciliation)
    ('clinicaltrials', 'api', 'https://clinicaltrials.gov/api/v2/studies',
     'ClinicalTrials.gov v2 API study records with eligibility, status, and trial design', 'weekly', TRUE),
    ('openfda_labels', 'api', 'https://api.fda.gov/drug/label.json',
     'FDA openFDA drug label (SPL) records with indications, warnings, and dosage information', 'weekly', TRUE),
    ('europepmc', 'api', 'https://www.ebi.ac.uk/europepmc/webservices/rest',
     'Europe PMC literature search for pharmaceutical and clinical research publications', 'daily', TRUE),
    ('euipo_designs', 'api', 'https://api.euipo.europa.eu/design-search/designs',
     'EUIPO registered industrial design search for pharmaceutical packaging and device designs', 'weekly', TRUE),
    ('nih_reporter', 'api', 'https://api.reporter.nih.gov/v2/projects/search',
     'NIH Research Portfolio Online Reporting Tools (RePORTER) funded research project grants', 'weekly', TRUE),
    ('hrsa', 'api', 'https://data.hrsa.gov',
     'HRSA Health Resources and Services Administration data including shortage areas and provider data', 'monthly', TRUE),
    ('who_icd', 'api', 'https://id.who.int/icd/release/11/2024-01/mms',
     'WHO ICD-10 and ICD-11 disease classification codes for diagnosis standardisation', 'annual', TRUE),
    ('who_inn', 'api', 'https://www.who.int/teams/health-product-and-policy-standards/inn',
     'WHO International Nonproprietary Names (INN) for pharmaceutical substances', 'monthly', TRUE),

    -- CMS Coverage / US HTA (021-post-deploy-fixes)
    ('cms_coverage', 'api', 'https://api.coverage.cms.gov/v1/data/',
     'CMS Medicare Coverage Database: NCDs, NCAs, and Technology Assessments (US HTA equivalent)', 'weekly', TRUE)

ON CONFLICT (source_name) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    description = EXCLUDED.description,
    refresh_frequency = EXCLUDED.refresh_frequency,
    is_active = EXCLUDED.is_active;

-- T107a: Update domain_schema for IP sources (001-silver-medallion-rebuild)
-- These sources feed ip_silver, not mol_silver
UPDATE meta.data_sources SET domain_schema = 'ip_silver'
WHERE source_name IN (
    'uspto_patents',
    'uspto_ci',
    'uspto_trademarks',
    'epo_ops',
    'euipo_trademarks',
    'euipo_designs'
)
  AND (domain_schema IS NULL OR domain_schema = 'mol_silver');

-- Set initial expected refresh frequencies
UPDATE meta.data_sources SET
    refresh_frequency = CASE source_name
        WHEN 'cms_medicare_inpatient' THEN 'quarterly'
        WHEN 'cms_hospital_info' THEN 'monthly'
        WHEN 'cms_cost_reports' THEN 'annual'
        WHEN 'acc_tvc' THEN 'quarterly'
        WHEN 'hrsa_shortage_areas' THEN 'monthly'
    END
WHERE source_name IN ('cms_medicare_inpatient', 'cms_hospital_info', 'cms_cost_reports', 'acc_tvc', 'hrsa_shortage_areas');

-- Output confirmation
DO $$
BEGIN
    RAISE NOTICE 'Data sources seeded successfully';
END
$$;

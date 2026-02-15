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

    ('uspto_patents', 'api', 'https://api.patentsview.org/patents/query',
     'USPTO PatentsView pharmaceutical patents with CPC code filtering', 'weekly', TRUE),

    -- Medium-impact CI sources (US5)
    ('journal_rss', 'rss', 'https://www.nejm.org/action/showFeed',
     'Journal RSS feeds from NEJM, Lancet, JAMA, BMJ, Nature Medicine', 'daily', TRUE),

    ('uspto_ci', 'api', 'https://api.patentsview.org/patents/query',
     'USPTO PatentsView CI pharma patents with query-scoped search terms', 'weekly', TRUE),

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
     'SEC EDGAR pharmaceutical company filings (10-K, 10-Q, 8-K)', 'daily', TRUE)

ON CONFLICT (source_name) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    description = EXCLUDED.description,
    refresh_frequency = EXCLUDED.refresh_frequency,
    is_active = EXCLUDED.is_active;

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

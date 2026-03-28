-- Migration 099: Schema prefix normalization
-- Ensures every table lives in a prefixed schema (mol_* or hcs_*).
-- No table is renamed — only the schema (namespace) changes.
--
-- Pattern:
--   raw.*       → mol_raw.*  (molecule raw ingestion)
--   raw.*       → hcs_raw.*  (healthcare/facility raw ingestion)
--   bronze.*    → mol_bronze.* or hcs_bronze.*
--   mol_silver.*    → mol_silver.* or hcs_silver.*
--   mol_gold.*      → mol_gold.*  (if any remained unprefixed)
--
-- Schemas mol_raw, mol_bronze, mol_silver, mol_gold, hcs_raw, hcs_bronze,
-- hcs_silver, hcs_gold are assumed to already exist from prior migrations.

BEGIN;

-- ============================================================
-- RAW → mol_raw  (molecule data sources)
-- ============================================================
ALTER TABLE IF EXISTS raw.bindingdb             SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.chembl                SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.clinicaltrials        SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.cochrane_reviews      SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.drugbank              SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.ema                   SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.epo_patents           SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.euipo_trademarks      SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.hta_decisions         SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.journal_rss           SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.medical_news          SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.openalex_ci           SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.openfda_faers         SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.openfda_labels        SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.orange_book           SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.orcid                 SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.pdb                   SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.pubchem               SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.pubmed                SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.sec_edgar             SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.sider                 SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.uniprot               SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.uspto_ci              SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.uspto_patents         SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.uspto_trademarks      SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.who_icd               SET SCHEMA mol_raw;

-- ============================================================
-- RAW → hcs_raw  (healthcare / facility data sources)
-- ============================================================
ALTER TABLE IF EXISTS raw.acc_tvc_certification  SET SCHEMA hcs_raw;
ALTER TABLE IF EXISTS raw.cms_cost_reports        SET SCHEMA hcs_raw;
ALTER TABLE IF EXISTS raw.cms_hospital_info       SET SCHEMA hcs_raw;
ALTER TABLE IF EXISTS raw.cms_medicare_inpatient  SET SCHEMA hcs_raw;
ALTER TABLE IF EXISTS raw.cms_geographic_variation SET SCHEMA hcs_raw;
ALTER TABLE IF EXISTS raw.hrsa_shortage_areas     SET SCHEMA hcs_raw;

-- ============================================================
-- BRONZE → mol_bronze  (molecule bronze tables)
-- SQLMesh manages the CREATE; this covers any hand-created or
-- legacy tables that were materialised into bronze.* directly.
-- ============================================================
ALTER TABLE IF EXISTS bronze.bindingdb             SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.chembl_molecules      SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.clinicaltrials         SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.cochrane_reviews       SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.drugbank               SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.ema                    SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.epo_patents            SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.euipo_trademarks       SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.europepmc              SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.faers_events           SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.hta_decisions          SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.journal_rss            SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.medical_news           SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.openalex               SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.openfda_labels         SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.orange_book            SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.orcid                  SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.pdb_structures         SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.pubchem                SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.pubmed                 SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.sec_edgar              SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.sider                  SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.uniprot                SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.uspto_ci               SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.uspto_patents          SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.uspto_trademarks       SET SCHEMA mol_bronze;
ALTER TABLE IF EXISTS bronze.who_icd                SET SCHEMA mol_bronze;

-- ============================================================
-- BRONZE → hcs_bronze  (healthcare / facility bronze tables)
-- ============================================================
ALTER TABLE IF EXISTS bronze.acc_tvc                    SET SCHEMA hcs_bronze;
ALTER TABLE IF EXISTS bronze.cms_cost_reports           SET SCHEMA hcs_bronze;
ALTER TABLE IF EXISTS bronze.cms_hospital_info          SET SCHEMA hcs_bronze;
ALTER TABLE IF EXISTS bronze.cms_inpatient              SET SCHEMA hcs_bronze;
ALTER TABLE IF EXISTS bronze.cms_geographic_variation   SET SCHEMA hcs_bronze;
ALTER TABLE IF EXISTS bronze.hrsa                       SET SCHEMA hcs_bronze;

-- ============================================================
-- SILVER → mol_silver  (molecule silver tables)
-- ============================================================
ALTER TABLE IF EXISTS mol_silver.admet_properties       SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.adverse_events         SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.bioactivity            SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.cdc_vaccines           SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.chembl                 SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.clinical_trials        SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.cochrane_reviews       SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.ct_gov_indication_stats SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.dailymed_labels        SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.drug_labels            SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.drug_spending          SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.drug_synonyms          SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.drugbank               SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.ema_regulatory         SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.financial_data         SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.hcpcs_molecule_bridge  SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.icd_codes              SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.icd10_indicator_mapping SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.identifier_mappings    SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.imgt                   SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.indication_epidemiology SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.indication_ontology    SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.indication_revenue     SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.journal_rss            SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.molecule_aliases       SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.molecule_publications  SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.molecule_targets       SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.molecules              SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.ndc_molecule_bridge    SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.news_signals           SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.patent_exclusivities   SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.patents                SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.pathways               SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.pharmacogenomics       SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.physician_payments     SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.physician_profiles     SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.protein_targets        SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.pubchem                SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.publication_evidence   SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.publications           SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.pubmed_articles        SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.regulatory_decisions   SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.regulatory_milestones  SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.rems_programs          SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.research_grants        SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.researchers            SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.rxnorm_concepts        SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.side_effects           SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.targets                SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.trademarks             SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.ttd                    SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.web_content            SET SCHEMA mol_silver;
ALTER TABLE IF EXISTS mol_silver.who_inn_names          SET SCHEMA mol_silver;

-- ============================================================
-- SILVER → hcs_silver  (healthcare / facility silver tables)
-- ============================================================
ALTER TABLE IF EXISTS mol_silver.geographic_health      SET SCHEMA hcs_silver;
ALTER TABLE IF EXISTS mol_silver.healthcare_facilities  SET SCHEMA hcs_silver;

COMMIT;

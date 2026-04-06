-- Migration 157: Switch TOAST compression from pglz to lz4 on all response_body columns
--
-- PostgreSQL 14+ supports lz4 TOAST compression which provides:
--   - 3-5x faster compression/decompression than pglz
--   - Similar or better compression ratios on JSON data
--   - Significant speedup for bronze transforms that read response_body via jsonb_array_elements()
--
-- This ALTER only changes the compression setting for NEW writes.
-- Existing data stays pglz-compressed until the table is rewritten (VACUUM FULL or pg_repack).
-- Both pglz and lz4 rows can coexist in the same table — PG auto-detects on read.
--
-- To recompress existing data (optional, requires table lock):
--   VACUUM FULL mol_raw.<table>;
--
-- Note: Only targets response_body JSONB columns in mol_raw and hcs_raw schemas.
-- New-schema tables (typed columns, no response_body) are unaffected.

-- mol_raw old-schema tables (35 tables with response_body)
ALTER TABLE mol_raw.bindingdb ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.cdc_vaccines ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.chembl ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.chembl_activities ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.clinicaltrials ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.cms_coverage ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.cms_medicare ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.dailymed ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.drugbank ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.ema ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.europepmc ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.fda_drugs ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.fda_ndc ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.fda_rems ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.imgt ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.kegg_drug ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.nice_hta ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.nih_reporter ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.npi_registry ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.openfda_faers ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.openfda_labels ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.orange_book ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.pdb ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.pharmgkb ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.pubchem ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.purple_book ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.reactome ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.rxnorm ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.sider ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.tdc_admet ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.ttd ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.uniprot ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.websearch ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.who_gho ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.who_icd ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE mol_raw.who_inn ALTER COLUMN response_body SET COMPRESSION lz4;

-- hcs_raw old-schema tables (17 tables with response_body)
ALTER TABLE hcs_raw.cms_care_compare ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_chow ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_ddinter ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_dmepos ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_formulary ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_hcris ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_hospital_affiliation ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_hospital_quality ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_magnet ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_ndc ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_nucc ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_pecos ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_pos ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_post_acute ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_rbcs ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_stabilis ALTER COLUMN response_body SET COMPRESSION lz4;
ALTER TABLE hcs_raw.cms_usp ALTER COLUMN response_body SET COMPRESSION lz4;

-- Also set the server default for any future tables
ALTER SYSTEM SET default_toast_compression = 'lz4';

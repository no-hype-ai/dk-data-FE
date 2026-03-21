-- Migration: 115_fix_deduplication.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Fix deduplication across all layers:
--   1. Add processed_to_bronze flag to 5 raw.* IP/patent tables missing it
--   2. Add unique constraints to mol_silver tables that had massive duplicates
--   3. Deduplicate any remaining rows

-- ─── Add processed_to_bronze to raw IP/patent tables ──────────────────────────

ALTER TABLE raw.epo_patents ADD COLUMN IF NOT EXISTS processed_to_bronze BOOLEAN DEFAULT FALSE;
ALTER TABLE raw.euipo_trademarks ADD COLUMN IF NOT EXISTS processed_to_bronze BOOLEAN DEFAULT FALSE;
ALTER TABLE raw.uspto_ci ADD COLUMN IF NOT EXISTS processed_to_bronze BOOLEAN DEFAULT FALSE;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS processed_to_bronze BOOLEAN DEFAULT FALSE;
ALTER TABLE raw.uspto_trademarks ADD COLUMN IF NOT EXISTS processed_to_bronze BOOLEAN DEFAULT FALSE;

-- Mark all existing rows as already processed (they've been through bronze)
UPDATE raw.epo_patents SET processed_to_bronze = TRUE WHERE processed_to_bronze = FALSE;
UPDATE raw.euipo_trademarks SET processed_to_bronze = TRUE WHERE processed_to_bronze = FALSE;
UPDATE raw.uspto_ci SET processed_to_bronze = TRUE WHERE processed_to_bronze = FALSE;
UPDATE raw.uspto_patents SET processed_to_bronze = TRUE WHERE processed_to_bronze = FALSE;
UPDATE raw.uspto_trademarks SET processed_to_bronze = TRUE WHERE processed_to_bronze = FALSE;

-- ─── Unique constraints on mol_silver tables ──────────────────────────────────
-- These prevent future duplicate insertion from repeated silver transforms

CREATE UNIQUE INDEX IF NOT EXISTS uq_regulatory_milestones_dedup
  ON mol_silver.regulatory_milestones (molecule_id, source, event_name, event_date);

CREATE UNIQUE INDEX IF NOT EXISTS uq_physician_payments_dedup
  ON mol_silver.physician_payments (molecule_id, physician_npi, physician_name, payment_year, payment_nature, payment_amount);

CREATE UNIQUE INDEX IF NOT EXISTS uq_adverse_events_dedup
  ON mol_silver.adverse_events (molecule_id, drug_name_reported, reaction_meddra_pt, report_date, patient_age, patient_sex);

CREATE UNIQUE INDEX IF NOT EXISTS uq_drug_labels_dedup
  ON mol_silver.drug_labels (application_number, brand_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_filings_dedup
  ON mol_silver.financial_filings (molecule_id, filing_type, filing_date, COALESCE(accession_number, ''));

CREATE UNIQUE INDEX IF NOT EXISTS uq_publications_dedup
  ON mol_silver.publications (doi) WHERE doi IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_protein_targets_dedup
  ON mol_silver.protein_targets (uniprot_accession) WHERE uniprot_accession IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_pathways_dedup
  ON mol_silver.pathways (pathway_name, pathway_source, molecule_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hta_decisions_dedup
  ON mol_silver.hta_decisions (molecule_id, agency, decision_date);

CREATE UNIQUE INDEX IF NOT EXISTS uq_clinical_trials_dedup
  ON mol_silver.clinical_trials (nct_id);

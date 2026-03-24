-- Migration: 120_restore_raw_jsonb_pattern.sql
-- Date: 2026-03-21
-- Description: Restore the original medallion design — all raw tables must store
--   the full API response as response_body JSONB. 14 tables were created with
--   typed columns only, causing data loss. This migration adds the standard
--   JSONB columns and backfills response_body from existing typed columns.
--   Existing typed columns are NOT dropped (backward compat).

-- ─── Step 1: Add standard JSONB columns to all 14 typed-column tables ────────

DO $$
DECLARE
  tbl TEXT;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'acc_tvc_certification', 'cochrane_reviews', 'ema_regulatory', 'epo_patents',
    'euipo_trademarks', 'hrsa_shortage_areas', 'journal_rss', 'medical_news',
    'openalex_ci', 'orcid', 'pubmed', 'uspto_ci', 'uspto_patents', 'uspto_trademarks'
  ])
  LOOP
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS response_body JSONB', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS response_body_hash VARCHAR(64)', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS request_id VARCHAR(100)', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS api_endpoint VARCHAR(500)', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS response_status INTEGER DEFAULT 200', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS processed_to_bronze BOOLEAN DEFAULT FALSE', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS source_id VARCHAR(50)', tbl);
    -- Indexes
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_resp_hash ON mol_raw.%I(response_body_hash)', tbl, tbl);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_processed ON mol_raw.%I(processed_to_bronze) WHERE processed_to_bronze = FALSE', tbl, tbl);
    RAISE NOTICE 'Added JSONB columns to mol_raw.%', tbl;
  END LOOP;
END $$;

-- ─── Step 2: Backfill response_body from existing typed columns ──────────────

-- pubmed
UPDATE mol_raw.pubmed SET response_body = jsonb_build_object(
  'pmid', pmid, 'title', title, 'abstract', abstract, 'authors', authors,
  'journal', journal, 'publication_date', publication_date,
  'mesh_terms', to_jsonb(mesh_terms), 'doi', doi,
  'publication_types', to_jsonb(publication_types), 'keywords', to_jsonb(keywords)
), source_id = 'pubmed', request_id = pmid
WHERE response_body IS NULL;

-- openalex_ci
UPDATE mol_raw.openalex_ci SET response_body = jsonb_build_object(
  'work_id', work_id, 'doi', doi, 'title', title, 'abstract', abstract,
  'publication_date', publication_date, 'cited_by_count', cited_by_count,
  'concepts', concepts, 'authorships', authorships,
  'primary_location', primary_location, 'open_access', open_access
), source_id = 'openalex_ci', request_id = work_id
WHERE response_body IS NULL;

-- ema_regulatory
UPDATE mol_raw.ema_regulatory SET response_body = jsonb_build_object(
  'document_id', document_id, 'document_type', document_type,
  'product_name', product_name, 'active_substance', active_substance,
  'therapeutic_area', therapeutic_area, 'decision_date', decision_date,
  'decision_type', decision_type, 'document_url', document_url, 'summary', summary
), source_id = 'ema_regulatory', request_id = document_id
WHERE response_body IS NULL;

-- journal_rss
UPDATE mol_raw.journal_rss SET response_body = jsonb_build_object(
  'article_id', article_id, 'feed_source', feed_source, 'title', title,
  'authors', authors, 'abstract', abstract, 'publication_date', publication_date,
  'link', link, 'doi', doi, 'categories', to_jsonb(categories)
), source_id = 'journal_rss', request_id = article_id
WHERE response_body IS NULL;

-- medical_news
UPDATE mol_raw.medical_news SET response_body = jsonb_build_object(
  'article_id', article_id, 'source_name', source_name, 'title', title,
  'summary', summary, 'publication_date', publication_date, 'url', url,
  'drug_mentions', to_jsonb(drug_mentions), 'therapeutic_areas', to_jsonb(therapeutic_areas)
), source_id = 'medical_news', request_id = article_id
WHERE response_body IS NULL;

-- cochrane_reviews
UPDATE mol_raw.cochrane_reviews SET response_body = jsonb_build_object(
  'review_id', review_id, 'title', title, 'authors', authors, 'abstract', abstract,
  'publication_date', publication_date, 'review_type', review_type,
  'interventions', to_jsonb(interventions), 'conditions', to_jsonb(conditions),
  'conclusions', conclusions, 'doi', doi
), source_id = 'cochrane_reviews', request_id = review_id
WHERE response_body IS NULL;

-- orcid (already has raw_response JSONB — use it)
UPDATE mol_raw.orcid SET response_body = COALESCE(raw_response, jsonb_build_object(
  'orcid_id', orcid_id, 'given_names', given_names, 'family_name', family_name,
  'credit_name', credit_name, 'biography', biography, 'keywords', keywords,
  'current_affiliations', current_affiliations, 'works_count', works_count,
  'external_ids', external_ids
)), source_id = 'orcid', request_id = orcid_id
WHERE response_body IS NULL;

-- epo_patents
UPDATE mol_raw.epo_patents SET response_body = jsonb_build_object(
  'publication_id', publication_id, 'title', title, 'abstract', abstract,
  'applicants', applicants, 'inventors', inventors, 'filing_date', filing_date,
  'publication_date', publication_date, 'ipc_codes', to_jsonb(ipc_codes),
  'family_id', family_id
), source_id = 'epo_patents', request_id = publication_id
WHERE response_body IS NULL;

-- euipo_trademarks
UPDATE mol_raw.euipo_trademarks SET response_body = jsonb_build_object(
  'application_number', application_number, 'mark_name', mark_name,
  'mark_kind', mark_kind, 'mark_feature', mark_feature, 'mark_basis', mark_basis,
  'applicant_name', applicant_name, 'applicant_country', applicant_country,
  'representative_name', representative_name, 'status', status,
  'filing_date', filing_date, 'registration_date', registration_date,
  'expiry_date', expiry_date, 'nice_classes', to_jsonb(nice_classes),
  'goods_and_services', goods_and_services, 'image_url', image_url
), source_id = 'euipo_trademarks', request_id = application_number
WHERE response_body IS NULL;

-- hrsa_shortage_areas
UPDATE mol_raw.hrsa_shortage_areas SET response_body = jsonb_build_object(
  'hpsa_id', hpsa_id, 'hpsa_name', hpsa_name, 'hpsa_type', hpsa_type,
  'designation_type', designation_type, 'state_abbr', state_abbr,
  'county_name', county_name, 'hpsa_score', hpsa_score,
  'designation_date', designation_date, 'rural_status', rural_status
), source_id = 'hrsa_shortage_areas', request_id = hpsa_id
WHERE response_body IS NULL;

-- acc_tvc_certification
UPDATE mol_raw.acc_tvc_certification SET response_body = jsonb_build_object(
  'facility_name', facility_name, 'facility_address', facility_address,
  'city', city, 'state', state, 'zip_code', zip_code,
  'certification_type', certification_type, 'certification_date', certification_date,
  'expiration_date', expiration_date
), source_id = 'acc_tvc_certification', request_id = facility_name
WHERE response_body IS NULL;

-- uspto_ci
UPDATE mol_raw.uspto_ci SET response_body = jsonb_build_object(
  'patent_id', patent_id, 'title', title, 'abstract', abstract,
  'inventors', inventors, 'assignees', assignees, 'filing_date', filing_date,
  'grant_date', grant_date, 'cpc_codes', to_jsonb(cpc_codes), 'claims_count', claims_count
), source_id = 'uspto_ci', request_id = patent_id
WHERE response_body IS NULL;

-- uspto_patents
UPDATE mol_raw.uspto_patents SET response_body = jsonb_build_object(
  'patent_number', patent_number, 'title', title, 'abstract', abstract,
  'inventors', inventors, 'assignees', assignees, 'filing_date', filing_date,
  'grant_date', grant_date, 'cpc_codes', to_jsonb(cpc_codes), 'claims_count', claims_count
), source_id = 'uspto_patents', request_id = patent_number
WHERE response_body IS NULL;

-- uspto_trademarks
UPDATE mol_raw.uspto_trademarks SET response_body = jsonb_build_object(
  'serial_number', serial_number, 'mark_element', mark_element,
  'mark_type', mark_type, 'status', status, 'status_code', status_code,
  'status_date', status_date, 'filing_date', filing_date,
  'registration_number', registration_number, 'registration_date', registration_date,
  'nice_classes', to_jsonb(nice_classes), 'us_classes', to_jsonb(us_classes),
  'owner_name', owner_name, 'owner_entity_type', owner_entity_type,
  'goods_and_services', goods_and_services, 'description_of_mark', description_of_mark
), source_id = 'uspto_trademarks', request_id = serial_number
WHERE response_body IS NULL;

-- ─── Step 3: Set processed_to_bronze = FALSE for backfilled rows ─────────────
-- This signals the dynamic transformer to process them

DO $$
DECLARE
  tbl TEXT;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'acc_tvc_certification', 'cochrane_reviews', 'ema_regulatory', 'epo_patents',
    'euipo_trademarks', 'hrsa_shortage_areas', 'journal_rss', 'medical_news',
    'openalex_ci', 'orcid', 'pubmed', 'uspto_ci', 'uspto_patents', 'uspto_trademarks'
  ])
  LOOP
    EXECUTE format('UPDATE mol_raw.%I SET processed_to_bronze = FALSE WHERE response_body IS NOT NULL AND processed_to_bronze IS NULL', tbl);
  END LOOP;
END $$;

-- ─── Step 4: Register missing sources in ops.sync_schedules ──────────────────

INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options) VALUES
  ('pubmed', 'weekly', '0 3 * * 1', 'normal', true, '{"source_name":"PubMed","api_type":"rest","target_table":"mol_raw.pubmed"}'::jsonb),
  ('openalex_ci', 'weekly', '0 3 * * 2', 'normal', true, '{"source_name":"OpenAlex CI","api_type":"rest","target_table":"mol_raw.openalex_ci"}'::jsonb),
  ('ema_regulatory', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"EMA Regulatory","api_type":"csv","target_table":"mol_raw.ema_regulatory"}'::jsonb),
  ('journal_rss', 'daily', '0 5 * * *', 'low', true, '{"source_name":"Journal RSS","api_type":"rss","target_table":"mol_raw.journal_rss"}'::jsonb),
  ('medical_news', 'daily', '0 6 * * *', 'low', true, '{"source_name":"Medical News","api_type":"rss","target_table":"mol_raw.medical_news"}'::jsonb),
  ('cochrane_reviews', 'monthly', '0 4 15 * *', 'normal', true, '{"source_name":"Cochrane Reviews","api_type":"rest","target_table":"mol_raw.cochrane_reviews"}'::jsonb),
  ('epo_patents', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"EPO Patents","api_type":"rest","target_table":"mol_raw.epo_patents"}'::jsonb),
  ('euipo_trademarks', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"EUIPO Trademarks","api_type":"scrape","target_table":"mol_raw.euipo_trademarks"}'::jsonb),
  ('hrsa_shortage_areas', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"HRSA Shortage Areas","api_type":"rest","target_table":"mol_raw.hrsa_shortage_areas"}'::jsonb),
  ('acc_tvc_certification', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"ACC TVC Certification","api_type":"csv","target_table":"mol_raw.acc_tvc_certification"}'::jsonb),
  ('uspto_ci', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"USPTO Citation Index","api_type":"rest","target_table":"mol_raw.uspto_ci"}'::jsonb),
  ('uspto_patents', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"USPTO Patents","api_type":"rest","target_table":"mol_raw.uspto_patents"}'::jsonb),
  ('uspto_trademarks', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"USPTO Trademarks","api_type":"rest","target_table":"mol_raw.uspto_trademarks"}'::jsonb)
ON CONFLICT (source) DO NOTHING;

-- ─── Step 5: Grants ──────────────────────────────────────────────────────────

DO $$
DECLARE
  tbl TEXT;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'acc_tvc_certification', 'cochrane_reviews', 'ema_regulatory', 'epo_patents',
    'euipo_trademarks', 'hrsa_shortage_areas', 'journal_rss', 'medical_news',
    'openalex_ci', 'orcid', 'pubmed', 'uspto_ci', 'uspto_patents', 'uspto_trademarks'
  ])
  LOOP
    EXECUTE format('GRANT SELECT ON mol_raw.%I TO analyst', tbl);
  END LOOP;
END $$;

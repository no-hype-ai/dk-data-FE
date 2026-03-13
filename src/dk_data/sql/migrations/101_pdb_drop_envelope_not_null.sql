-- Drop NOT NULL constraints on raw.pdb JSONB envelope columns.
-- The PDB loader inserts structured columns (pdb_id, title, method, resolution,
-- deposit_date, raw_response) added in migration 099, but the original table
-- from migration 028 has NOT NULL on the envelope columns (request_id,
-- request_timestamp, api_endpoint, response_status, response_body, source_id).
-- These block the structured inserts.
-- Feature: 016-cms-puf-datasource-integration

ALTER TABLE raw.pdb ALTER COLUMN request_id DROP NOT NULL;
ALTER TABLE raw.pdb ALTER COLUMN request_timestamp DROP NOT NULL;
ALTER TABLE raw.pdb ALTER COLUMN api_endpoint DROP NOT NULL;
ALTER TABLE raw.pdb ALTER COLUMN response_status DROP NOT NULL;
ALTER TABLE raw.pdb ALTER COLUMN response_body DROP NOT NULL;
ALTER TABLE raw.pdb ALTER COLUMN ingested_at DROP NOT NULL;
ALTER TABLE raw.pdb ALTER COLUMN source_id DROP NOT NULL;

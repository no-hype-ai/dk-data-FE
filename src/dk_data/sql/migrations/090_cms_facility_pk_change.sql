-- Migration 090: Healthcare Facilities PK Change (016-cms-puf-datasource-integration)
--
-- Changes healthcare_facilities primary key from (provider_id, source) to ccn
-- Integration point §E from spec
-- T063

BEGIN;

-- Add ccn column if it doesn't exist
ALTER TABLE silver.healthcare_facilities
    ADD COLUMN IF NOT EXISTS ccn VARCHAR(10);

-- Backfill ccn from provider_id where possible
UPDATE silver.healthcare_facilities
SET ccn = provider_id
WHERE ccn IS NULL AND provider_id IS NOT NULL;

-- Drop old primary key constraint
ALTER TABLE silver.healthcare_facilities
    DROP CONSTRAINT IF EXISTS healthcare_facilities_pkey;

-- Add new primary key on ccn
ALTER TABLE silver.healthcare_facilities
    ADD CONSTRAINT healthcare_facilities_pkey PRIMARY KEY (ccn);

-- Add index on old columns for backward compatibility
CREATE INDEX IF NOT EXISTS idx_healthcare_facilities_provider_source
    ON silver.healthcare_facilities (provider_id, source);

COMMIT;

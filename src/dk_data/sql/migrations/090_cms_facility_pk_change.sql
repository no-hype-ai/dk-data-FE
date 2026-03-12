-- Migration 090: Healthcare Facilities PK Change (016-cms-puf-datasource-integration)
--
-- Changes healthcare_facilities primary key from (provider_id, source) to ccn
-- Integration point §E from spec
-- T063
--
-- NOTE: silver.healthcare_facilities is materialised by SQLMesh, so it may
-- not exist when migrations run in CI before model backfill.  The DO block
-- guards every statement so the migration is a safe no-op in that case.

DO $$
BEGIN
    -- Only proceed if the table already exists (it is created by SQLMesh)
    IF EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'silver' AND table_name = 'healthcare_facilities'
    ) THEN
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

        RAISE NOTICE 'Migration 090: healthcare_facilities PK changed to ccn';
    ELSE
        RAISE NOTICE 'Migration 090: silver.healthcare_facilities does not exist yet — skipping (will apply after SQLMesh backfill)';
    END IF;
END $$;

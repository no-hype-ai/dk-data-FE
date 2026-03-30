-- Migration 125: Fix HCS unique constraints to match actual source data
--
-- Two constraints added in migration 118 don't match what the loaders actually insert:
--
-- 1. cms_medicare_advantage:
--    Migration 118 added UNIQUE (contract_id, plan_id, segment_id, county_fips, _source_year)
--    but the UUID 8e989bc0 dataset is geographic-level enrollment data — contract_id, plan_id,
--    and segment_id are all NULL. The source loader uses (_source_hash, enrollment_data_period,
--    fips_cd) as the conflict key. Drop the broken plan-level constraint and add the correct one.
--
-- 2. cms_referring_providers:
--    Migration 118 added UNIQUE (rndrng_npi, rfrd_npi, _source_year) but the UUID c99b5865
--    dataset is a single-NPI PECOS eligibility list — rfrd_npi is always NULL. PostgreSQL
--    NULL != NULL in unique indexes, so this constraint does not enforce uniqueness and the
--    source loader's ON CONFLICT (rndrng_npi, _source_year) won't match it.
--    Drop the broken two-column constraint and add the correct single-NPI constraint.

-- 1. cms_medicare_advantage: replace plan-level constraint with geographic-level constraint
DO $$ BEGIN
    -- Drop the old constraint (only if it exists)
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_medicare_advantage_key'
          AND conrelid = 'hcs_raw.cms_medicare_advantage'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_medicare_advantage
            DROP CONSTRAINT uq_cms_medicare_advantage_key;
    END IF;

    -- Add the correct constraint matching the source loader's conflict columns
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_medicare_advantage_geo'
          AND conrelid = 'hcs_raw.cms_medicare_advantage'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_medicare_advantage
            ADD CONSTRAINT uq_cms_medicare_advantage_geo
            UNIQUE (_source_hash, enrollment_data_period, fips_cd);
    END IF;
END $$;

-- 2. cms_referring_providers: replace two-column (NPI+rfrd_npi) with single-NPI constraint
DO $$ BEGIN
    -- Drop the old constraint (only if it exists)
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_referring_providers_key'
          AND conrelid = 'hcs_raw.cms_referring_providers'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_referring_providers
            DROP CONSTRAINT uq_cms_referring_providers_key;
    END IF;

    -- Add the correct constraint matching the source loader's conflict columns
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_referring_providers_npi_year'
          AND conrelid = 'hcs_raw.cms_referring_providers'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_referring_providers
            ADD CONSTRAINT uq_cms_referring_providers_npi_year
            UNIQUE (rndrng_npi, _source_year);
    END IF;
END $$;

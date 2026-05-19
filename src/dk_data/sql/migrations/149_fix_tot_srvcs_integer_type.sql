-- Migration 149: Fix tot_srvcs column type from INTEGER to NUMERIC(18,2)
--
-- Context:
--   Migration 092 correctly defined tot_srvcs as NUMERIC(18,2) in cms_mental_health_puf
--   and cms_telehealth_puf. Migration 117 (cms_puf_agent_schema_fixes) re-created those
--   tables with tot_srvcs INTEGER, overriding the correct type.
--
--   Similarly, cms_ordering_providers and cms_referring_providers were created in 117
--   with tot_srvcs INTEGER. CMS PUF data contains fractional service counts (e.g. "73.5")
--   which are suppressed/averaged values for low-volume providers — they cannot be stored
--   as INTEGER without data loss.
--
--   This migration is idempotent: ALTER COLUMN … TYPE is a no-op if the column is already
--   NUMERIC(18,2).
--
-- Tables fixed:
--   hcs_raw.cms_mental_health_puf   (tot_srvcs: INTEGER → NUMERIC(18,2))
--   hcs_raw.cms_telehealth_puf      (tot_srvcs: INTEGER → NUMERIC(18,2))
--   hcs_raw.cms_ordering_providers  (tot_srvcs: INTEGER → NUMERIC(18,2))
--   hcs_raw.cms_referring_providers (tot_srvcs: INTEGER → NUMERIC(18,2))

BEGIN;

DO $$
BEGIN
    IF to_regclass('hcs_raw.cms_mental_health_puf') IS NOT NULL THEN
        ALTER TABLE hcs_raw.cms_mental_health_puf
            ALTER COLUMN tot_srvcs TYPE NUMERIC(18,2) USING tot_srvcs::NUMERIC;
        RAISE NOTICE 'Fixed hcs_raw.cms_mental_health_puf.tot_srvcs → NUMERIC(18,2)';
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('hcs_raw.cms_telehealth_puf') IS NOT NULL THEN
        ALTER TABLE hcs_raw.cms_telehealth_puf
            ALTER COLUMN tot_srvcs TYPE NUMERIC(18,2) USING tot_srvcs::NUMERIC;
        RAISE NOTICE 'Fixed hcs_raw.cms_telehealth_puf.tot_srvcs → NUMERIC(18,2)';
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('hcs_raw.cms_ordering_providers') IS NOT NULL THEN
        ALTER TABLE hcs_raw.cms_ordering_providers
            ALTER COLUMN tot_srvcs TYPE NUMERIC(18,2) USING tot_srvcs::NUMERIC;
        RAISE NOTICE 'Fixed hcs_raw.cms_ordering_providers.tot_srvcs → NUMERIC(18,2)';
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('hcs_raw.cms_referring_providers') IS NOT NULL THEN
        ALTER TABLE hcs_raw.cms_referring_providers
            ALTER COLUMN tot_srvcs TYPE NUMERIC(18,2) USING tot_srvcs::NUMERIC;
        RAISE NOTICE 'Fixed hcs_raw.cms_referring_providers.tot_srvcs → NUMERIC(18,2)';
    END IF;
END $$;

COMMIT;

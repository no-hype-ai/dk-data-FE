-- Migration: 222_deprecate_molecule_profile_plural
-- Feature: 002-external-integration-foundation (US-10, T138)
-- Purpose: Mark `mol_gold.molecule_profiles` (plural) as deprecated.
--          The singular form `mol_gold.molecule_profile` is the
--          canonical table — see docs/decisions/molecule-profile-canonical.md
--
-- This migration ADDS a COMMENT ON TABLE warning any operator who
-- runs `\d+ mol_gold.molecule_profiles` that the table is going away.
-- The actual DROP of the plural table + `mart.molecule_360` happens
-- in a FOLLOW-UP migration (223) after a 14-day grace period — that
-- lets us catch any straggler consumer via `pg_stat_user_tables`
-- before the DROP fires.
--
-- Why this migration exists separately from 216: US-10 is a
-- documentation-and-observability task, not the main feature 002
-- schema work. Keeping it in its own file lets reviewers audit it
-- without pulling the entire feature bundle through code review.
--
-- No DML on business data. No grants. Pure COMMENT ON TABLE.
--
-- Run: psql ... -f migrations/222_deprecate_molecule_profile_plural.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
    -- Only emit the comment if the plural table actually exists; a
    -- fresh install built from the silver-hub bootstrap already skips
    -- creating the plural form, so this is a best-effort annotation.
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_gold' AND table_name = 'molecule_profiles'
    ) THEN
        EXECUTE 'COMMENT ON TABLE mol_gold.molecule_profiles IS '
             || quote_literal(
                'DEPRECATED (feature 002-external-integration-foundation US-10): '
                'this is the legacy plural table from migration 020. The canonical '
                'table is mol_gold.molecule_profile (singular) — created by migration '
                '081 and maintained by SQLMesh. This plural table will be DROPPED '
                'in migration 223 (~14 days after 222 lands in production). See '
                'docs/decisions/molecule-profile-canonical.md for the decision log. '
                'DO NOT add new consumers of this table.'
             );
        RAISE NOTICE 'deprecated mol_gold.molecule_profiles (plural form) — '
                     'readers should switch to mol_gold.molecule_profile';
    ELSE
        RAISE NOTICE 'mol_gold.molecule_profiles does not exist — nothing to deprecate';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mart' AND table_name = 'molecule_360'
    ) THEN
        EXECUTE 'COMMENT ON TABLE mart.molecule_360 IS '
             || quote_literal(
                'DEPRECATED (feature 002-external-integration-foundation US-10): '
                'this view reads from mol_gold.molecule_profiles (plural, deprecated). '
                'It has had zero reads since 2025-11-01 per pg_stat_user_tables. '
                'Will be DROPPED in migration 223. See '
                'docs/decisions/molecule-profile-canonical.md.'
             );
        RAISE NOTICE 'deprecated mart.molecule_360 (sole consumer of plural form)';
    END IF;
END $$;

DO $$
BEGIN
    RAISE NOTICE '222_deprecate_molecule_profile_plural complete';
    RAISE NOTICE 'Next step: wait 14 days, recheck pg_stat_user_tables, then run migration 223';
END $$;

COMMIT;

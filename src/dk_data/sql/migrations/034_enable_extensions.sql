-- Migration: 034_enable_extensions.sql
-- Description: Enable PostgreSQL extensions required for DK Data Platform
-- Date: 2026-01-23
-- Part of: 012-dk-data-platform

-- ==========================================
-- pg_trgm: Trigram-based fuzzy text matching
-- Used for fuzzy molecule name search
-- ==========================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create GIN index for fuzzy matching on molecule aliases
-- This enables fast similarity searches using % operator
CREATE INDEX IF NOT EXISTS idx_alias_trgm ON silver_molecule_aliases
    USING gin (alias_name_normalized gin_trgm_ops);

-- ==========================================
-- pgcrypto: Cryptographic functions
-- Used for secure credential storage
-- ==========================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ==========================================
-- uuid-ossp: UUID generation (fallback)
-- Note: gen_random_uuid() from pgcrypto is preferred
-- ==========================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- Verify Extensions
-- ==========================================

DO $$
BEGIN
    -- Check pg_trgm is working
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        RAISE EXCEPTION 'pg_trgm extension not installed';
    END IF;

    -- Test similarity function
    PERFORM similarity('aspirin', 'aspirn');

    RAISE NOTICE 'All required extensions verified successfully';
END $$;

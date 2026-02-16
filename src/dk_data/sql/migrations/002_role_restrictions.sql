-- Role Restrictions Migration
-- Feature: 002-production-readiness
-- Tasks: T097, T098, T099, T100
--
-- This migration restricts API access based on user roles.
-- It implements the RBAC model defined in the specification:
--   - web_anon: Health check and data catalog only (anonymous)
--   - analyst: Read access to targets, scoring, data_sources
--   - api_user: Full read access to all API tables
--
-- JWT Token Structure:
--   {
--     "role": "analyst",           -- Required: one of web_anon, analyst, api_user
--     "exp": 1735689600,           -- Required: expiration timestamp
--     "iat": 1735603200,           -- Optional: issued at timestamp
--     "sub": "user@example.com"    -- Optional: subject identifier
--   }
--
-- Usage:
--   curl -H "Authorization: Bearer <jwt_token>" https://api.example.com/targets

-- ============================================================================
-- Revoke all permissions from web_anon (T098)
-- ============================================================================
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA api FROM web_anon;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA api FROM web_anon;

-- Grant minimal permissions to web_anon
-- Only health check (via root endpoint) and data catalog are public
GRANT USAGE ON SCHEMA api TO web_anon;

-- Health endpoint is handled by PostgREST root
-- Data catalog - public access for discovery
GRANT SELECT ON api.data_catalog TO web_anon;

-- If health table exists, grant access
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'api' AND table_name = 'health') THEN
        EXECUTE 'GRANT SELECT ON api.health TO web_anon';
    END IF;
END $$;

-- ============================================================================
-- Configure analyst role (T099)
-- ============================================================================
-- Drop role if exists and recreate to ensure clean state
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA api TO analyst;

-- Analyst can view targets, scoring, and data sources
-- Use IF EXISTS guards for views that may not yet be created in all environments
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'api' AND table_name = 'targets') THEN
        EXECUTE 'GRANT SELECT ON api.targets TO analyst';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'api' AND table_name = 'scoring') THEN
        EXECUTE 'GRANT SELECT ON api.scoring TO analyst';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'api' AND table_name = 'data_sources') THEN
        EXECUTE 'GRANT SELECT ON api.data_sources TO analyst';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'api' AND table_name = 'data_catalog') THEN
        EXECUTE 'GRANT SELECT ON api.data_catalog TO analyst';
    END IF;
END $$;

-- Analyst can also view metadata
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'api' AND table_name = 'recommendations') THEN
        EXECUTE 'GRANT SELECT ON api.recommendations TO analyst';
    END IF;
END $$;

-- ============================================================================
-- Configure api_user role (T100)
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
        CREATE ROLE api_user NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA api TO api_user;

-- api_user has full read access to all API tables
GRANT SELECT ON ALL TABLES IN SCHEMA api TO api_user;

-- Future tables in api schema also get read access
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO api_user;

-- ============================================================================
-- Grant web_anon as default for PostgREST
-- ============================================================================
-- PostgREST uses web_anon as the default role for unauthenticated requests
-- JWT tokens can elevate to analyst or api_user via the role claim

-- ============================================================================
-- Verification queries (run manually to verify)
-- ============================================================================
--
-- -- Check web_anon permissions (should only see data_catalog)
-- SELECT grantee, table_name, privilege_type
-- FROM information_schema.table_privileges
-- WHERE grantee = 'web_anon' AND table_schema = 'api';
--
-- -- Check analyst permissions
-- SELECT grantee, table_name, privilege_type
-- FROM information_schema.table_privileges
-- WHERE grantee = 'analyst' AND table_schema = 'api';
--
-- -- Check api_user permissions
-- SELECT grantee, table_name, privilege_type
-- FROM information_schema.table_privileges
-- WHERE grantee = 'api_user' AND table_schema = 'api';

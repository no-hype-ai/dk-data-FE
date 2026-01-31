# Data Model: Prioritized Issue Resolution

**Feature**: 005-prioritized-issue-resolution
**Date**: 2026-01-30

## Overview

This document defines the database roles, permissions, and API views required for secure PostgREST access. The model enforces role-based access control (RBAC) with explicit permission grants.

## Database Roles

### Role Hierarchy

```
postgres (superuser)
    │
    └── authenticator (LOGIN, NOINHERIT)
            │
            ├── web_anon (NOLOGIN) ─── Public/unauthenticated access
            ├── analyst (NOLOGIN) ──── Read-only TAVR data access
            ├── api_user (NOLOGIN) ─── Full API read + molecule write
            └── readonly (LOGIN) ───── Direct DB read access (debugging)
```

### Role Definitions

| Role | Type | Purpose | Inherits From |
|------|------|---------|---------------|
| `authenticator` | LOGIN, NOINHERIT | PostgREST connection role; switches to other roles via JWT | None |
| `web_anon` | NOLOGIN | Unauthenticated API access; health checks only | None |
| `analyst` | NOLOGIN | Read TAVR targeting and scoring data | None |
| `api_user` | NOLOGIN | Full API read + molecule pipeline write | None |
| `readonly` | LOGIN | Direct database access for debugging | None |

### Role to Authenticator Grants

```sql
GRANT web_anon TO authenticator;
GRANT analyst TO authenticator;
GRANT api_user TO authenticator;
-- readonly is LOGIN role, not granted to authenticator
```

## Schema Permissions

### TAVR Schemas

| Schema | web_anon | analyst | api_user | readonly |
|--------|----------|---------|----------|----------|
| `api` | health, data_catalog only | targets, scoring, data_sources, data_catalog | ALL | ALL |
| `raw` | - | - | - | SELECT |
| `staging` | - | - | - | SELECT |
| `mart` | - | - | SELECT | SELECT |
| `scoring` | - | - | - | SELECT |
| `meta` | - | - | - | SELECT |

### Molecule Schemas

| Schema | web_anon | analyst | api_user | readonly |
|--------|----------|---------|----------|----------|
| `mol_api` | SELECT | SELECT | SELECT | SELECT |
| `mol_raw` | - | - | ALL | SELECT |
| `mol_bronze` | - | - | ALL | SELECT |
| `mol_silver` | - | - | ALL | SELECT |
| `mol_gold` | - | - | ALL | SELECT |
| `mol_app` | - | - | ALL | SELECT |

## API Views

### Public Views (web_anon accessible)

#### api.health

Health check endpoint for Kubernetes probes.

| Column | Type | Description |
|--------|------|-------------|
| `status` | text | Always 'ok' if database is accessible |
| `timestamp` | timestamptz | Current server time |
| `database` | text | Database name (dk_data) |

```sql
CREATE OR REPLACE VIEW api.health AS
SELECT
  'ok'::text AS status,
  now() AS timestamp,
  current_database() AS database;

GRANT SELECT ON api.health TO web_anon;
```

#### api.data_catalog

Metadata about available data sources.

| Column | Type | Description |
|--------|------|-------------|
| `schemaname` | name | Schema containing the table |
| `tablename` | name | Table name |
| `row_count` | bigint | Approximate row count |
| `last_vacuum` | timestamptz | Last vacuum time |
| `last_analyze` | timestamptz | Last analyze time |

```sql
CREATE OR REPLACE VIEW api.data_catalog AS
SELECT
  schemaname,
  tablename,
  n_live_tup AS row_count,
  last_vacuum,
  last_analyze
FROM pg_stat_user_tables
WHERE schemaname IN ('raw', 'staging', 'mart', 'mol_raw', 'mol_bronze', 'mol_silver', 'mol_gold')
ORDER BY schemaname, tablename;

GRANT SELECT ON api.data_catalog TO web_anon;
GRANT SELECT ON api.data_catalog TO analyst;
GRANT SELECT ON api.data_catalog TO api_user;
```

### Protected Views (analyst/api_user accessible)

#### api.targets

Hospital targeting data (placeholder - depends on underlying tables).

| Column | Type | Description |
|--------|------|-------------|
| `hospital_id` | text | Hospital identifier |
| `name` | text | Hospital name |
| `tier` | text | Targeting tier (A/B/C) |
| `score` | numeric | Composite targeting score |
| `updated_at` | timestamptz | Last score update |

```sql
-- Placeholder view if underlying tables don't exist
CREATE OR REPLACE VIEW api.targets AS
SELECT
  'placeholder'::text AS hospital_id,
  'No data loaded'::text AS name,
  'N/A'::text AS tier,
  0::numeric AS score,
  now() AS updated_at
WHERE false;  -- Empty by default

GRANT SELECT ON api.targets TO analyst;
GRANT SELECT ON api.targets TO api_user;
```

#### api.scoring

Scoring breakdown details (placeholder).

| Column | Type | Description |
|--------|------|-------------|
| `hospital_id` | text | Hospital identifier |
| `factor` | text | Scoring factor name |
| `weight` | numeric | Factor weight |
| `score` | numeric | Factor score |

```sql
CREATE OR REPLACE VIEW api.scoring AS
SELECT
  'placeholder'::text AS hospital_id,
  'No data loaded'::text AS factor,
  0::numeric AS weight,
  0::numeric AS score
WHERE false;

GRANT SELECT ON api.scoring TO analyst;
GRANT SELECT ON api.scoring TO api_user;
```

#### api.data_sources

Data source configuration (placeholder).

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | text | Data source identifier |
| `source_type` | text | Type (API, file, etc.) |
| `last_fetch` | timestamptz | Last successful fetch |
| `status` | text | Current status |

```sql
CREATE OR REPLACE VIEW api.data_sources AS
SELECT
  'placeholder'::text AS source_name,
  'none'::text AS source_type,
  now() AS last_fetch,
  'pending'::text AS status
WHERE false;

GRANT SELECT ON api.data_sources TO analyst;
GRANT SELECT ON api.data_sources TO api_user;
```

## JWT Claims

PostgREST uses JWT claims to switch roles. The token payload must include:

| Claim | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | Yes | PostgreSQL role to assume (analyst, api_user) |
| `exp` | number | Yes | Expiration timestamp (Unix epoch) |
| `iat` | number | No | Issued-at timestamp |
| `sub` | string | No | Subject identifier (user/service ID) |

### Example JWT Payload

```json
{
  "role": "analyst",
  "exp": 1738339200,
  "iat": 1738252800,
  "sub": "user:analyst@example.com"
}
```

### JWT Secret Requirements

- **Algorithm**: HS256 (HMAC-SHA256)
- **Minimum Length**: 32 characters (256 bits)
- **Source**: Doppler secret management
- **Key Name**: `PGRST_JWT_SECRET`

## Permission SQL Summary

```sql
-- Clean slate for web_anon
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA api FROM web_anon;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_api FROM web_anon;

-- web_anon: only health and data_catalog
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON api.health TO web_anon;
GRANT SELECT ON api.data_catalog TO web_anon;
GRANT USAGE ON SCHEMA mol_api TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_api TO web_anon;

-- analyst: TAVR read access
GRANT USAGE ON SCHEMA api TO analyst;
GRANT SELECT ON api.targets TO analyst;
GRANT SELECT ON api.scoring TO analyst;
GRANT SELECT ON api.data_sources TO analyst;
GRANT SELECT ON api.data_catalog TO analyst;

-- api_user: full API read + molecule write
GRANT USAGE ON SCHEMA api TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO api_user;

-- Molecule schema write access for api_user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_raw TO api_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_bronze TO api_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_silver TO api_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_gold TO api_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_app TO api_user;

-- readonly: direct access for debugging
GRANT USAGE ON SCHEMA api, mart TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO readonly;
```

## Entity Relationships

```
┌─────────────────┐         ┌─────────────────┐
│   api.health    │         │ api.data_catalog│
│  (public view)  │         │  (public view)  │
└─────────────────┘         └─────────────────┘

┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   api.targets   │◄────────│  api.scoring    │         │ api.data_sources│
│(hospital scores)│ 1:many  │(score breakdown)│         │  (source meta)  │
└─────────────────┘         └─────────────────┘         └─────────────────┘
        │
        │ hospital_id
        ▼
┌─────────────────┐
│  mart.hospitals │
│  (source data)  │
└─────────────────┘
```

## Notes

1. **Placeholder Views**: The targets, scoring, and data_sources views are created as empty placeholders. They will be populated once underlying tables exist from data ingestion.

2. **mol_api Schema**: The molecule platform uses a separate schema (`mol_api`) for its public API views. `web_anon` has full SELECT access to this schema for public compound searches.

3. **Default Privileges**: `ALTER DEFAULT PRIVILEGES` ensures new tables created in these schemas automatically get the correct permissions.

4. **Role Hierarchy**: PostgREST connects as `authenticator` and uses `SET ROLE` to switch to the role specified in the JWT. The `NOINHERIT` option ensures explicit role switching is required.

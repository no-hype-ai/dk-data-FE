# Data Model: Observability & Platform Governance

**Feature**: 013-observability-governance
**Date**: 2026-02-15

---

## New Entities

### 1. meta.api_audit_log

Immutable record of API access events and data ingestion operations. Supports both job-trigger middleware writes and PostgreSQL trigger writes from PostgREST API view access.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Auto-incrementing row ID |
| request_id | UUID | NOT NULL | Correlation ID (from X-Request-ID header or generated) |
| timestamp | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Event timestamp |
| source | VARCHAR(20) | NOT NULL, DEFAULT 'job-trigger' | Origin: 'job-trigger', 'postgrest', 'cronjob' |
| method | VARCHAR(10) | | HTTP method (GET, POST, etc.) — NULL for cronjob events |
| path | TEXT | | Endpoint path — NULL for cronjob events |
| query_params | JSONB | | Request query parameters |
| user_role | VARCHAR(50) | | JWT role claim (web_anon, analyst, api_user) |
| user_sub | VARCHAR(255) | | JWT sub claim (user identifier) |
| ip_address | INET | | Client IP (from X-Forwarded-For or remote_addr) |
| user_agent | TEXT | | Client user-agent header |
| status_code | SMALLINT | | HTTP response status code |
| response_time_ms | INTEGER | | Response duration in milliseconds |
| action | VARCHAR(50) | | Audit action type (from AuditAction enum) |
| category | VARCHAR(20) | | Audit category (from AuditCategory enum) |
| details | JSONB | | Additional context (source_name, record_count, error_message) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Row creation timestamp |

**Indexes**:
- `idx_api_audit_timestamp` on `(timestamp DESC)` — time-range queries
- `idx_api_audit_user_role` on `(user_role)` — role-based filtering
- `idx_api_audit_path` on `(path)` — endpoint filtering
- `idx_api_audit_category` on `(category)` — category filtering

**Access control**:
- INSERT: `api_user`, `analyst` (via triggers/middleware)
- SELECT: `api_user` only (admin-level access per clarification)
- UPDATE/DELETE: REVOKED from all roles (append-only)

**Retention**: 1 year for access events (`category = 'system'`), 7 years for data change events (`category IN ('data_source', 'admin')`)

---

### 2. meta.schema_migrations

Tracks which SQL migration files have been applied to the database. Used by the migration runner to determine pending migrations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-incrementing row ID |
| version | VARCHAR(10) | NOT NULL, UNIQUE | Migration number prefix (e.g., '001', '020', '066') |
| filename | VARCHAR(255) | NOT NULL | Full migration filename (e.g., '066_orcid_raw_table.sql') |
| checksum | VARCHAR(64) | NOT NULL | SHA-256 hash of file contents at time of application |
| applied_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | When the migration was applied |
| applied_by | VARCHAR(100) | DEFAULT 'migration-runner' | Who/what applied it (runner, baseline, manual) |
| execution_time_ms | INTEGER | | How long the migration took to execute |

**Indexes**:
- UNIQUE on `version` — prevents duplicate application
- `idx_schema_migrations_applied_at` on `(applied_at DESC)` — chronological queries

**Access control**:
- Full access: superuser (migration runner runs as DB owner)
- SELECT: `api_user` (for migration status API view)

---

### 3. meta.data_classification

Table-level metadata recording the data sensitivity classification for every table in the database.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-incrementing row ID |
| schema_name | VARCHAR(50) | NOT NULL | PostgreSQL schema name |
| table_name | VARCHAR(100) | NOT NULL | Table name |
| classification | VARCHAR(20) | NOT NULL, CHECK IN ('public', 'internal', 'pii', 'confidential') | Sensitivity level |
| pii_fields | TEXT[] | | Array of column names containing PII (NULL if classification != 'pii') |
| retention_days | INTEGER | | Retention period in days (NULL = perpetual) |
| retention_policy | VARCHAR(50) | | Reference to purge strategy ('rolling_window', 'archive_then_purge', 'perpetual') |
| notes | TEXT | | Additional context or justification |
| classified_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | When classification was assigned |
| classified_by | VARCHAR(100) | DEFAULT 'seed' | Who assigned it (seed, manual, audit) |

**Indexes**:
- UNIQUE on `(schema_name, table_name)` — one classification per table
- `idx_data_classification_level` on `(classification)` — filter by sensitivity

**Access control**:
- SELECT: `api_user` (admin can review classifications)
- INSERT/UPDATE: superuser only (classification changes are administrative)

---

## Existing Entities (Referenced, Not Modified)

### meta.refresh_log (existing)

Already tracks data ingestion operations. No schema changes needed — continue using for operational audit of CronJob runs (US3 acceptance scenario 2).

### meta.data_sources (existing)

Add `retention_days` column to support per-source retention policy (US5). This extends the existing seed_data_sources.sql entries.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| retention_days | INTEGER | DEFAULT NULL | Data retention period in days (NULL = use classification default) |

---

## API Views (New)

### api.audit_log

PostgREST-queryable view over `meta.api_audit_log` for compliance review.

```sql
CREATE OR REPLACE VIEW api.audit_log AS
SELECT id, request_id, timestamp, source, method, path,
       user_role, user_sub, status_code, response_time_ms,
       action, category, details, created_at
FROM meta.api_audit_log
ORDER BY timestamp DESC;
```

**Access**: `api_user` only (GRANT SELECT; REVOKE from web_anon, analyst)

### api.migration_status

Read-only view of applied migrations for operational visibility.

```sql
CREATE OR REPLACE VIEW api.migration_status AS
SELECT version, filename, applied_at, applied_by, execution_time_ms
FROM meta.schema_migrations
ORDER BY version;
```

**Access**: `api_user` only

### api.data_classification

Read-only view of table classification levels.

```sql
CREATE OR REPLACE VIEW api.data_classification AS
SELECT schema_name, table_name, classification, pii_fields,
       retention_days, retention_policy, notes
FROM meta.data_classification
ORDER BY classification, schema_name, table_name;
```

**Access**: `api_user` only

---

## Entity Relationships

```
meta.data_sources (existing)
  └── retention_days (new column) → references meta.data_classification.retention_days default

meta.api_audit_log (new)
  └── category → maps to AuditCategory enum in application code
  └── action → maps to AuditAction enum in application code

meta.schema_migrations (new)
  └── version → corresponds to migration filename prefix in src/dk_data/sql/migrations/

meta.data_classification (new)
  └── (schema_name, table_name) → references actual PostgreSQL tables
  └── retention_days → consumed by purge_history.py (extended)
```

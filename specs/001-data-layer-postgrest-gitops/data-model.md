# Data Model: Data Layer Enhancement with PostgREST and GitOps

**Feature**: 001-data-layer-postgrest-gitops
**Date**: 2026-01-14

## Overview

This document describes the data model enhancements required for the data catalog, health monitoring, and batch job tracking features.

## Schema Organization

```
PostgreSQL Database: edwards_tavr
├── raw.*          # Unmodified source data (existing)
├── staging.*      # Cleaned, standardized data (existing)
├── mart.*         # Analytics-ready dimensions/facts (existing)
├── scoring.*      # Target scoring calculations (existing)
├── meta.*         # Metadata and catalog (ENHANCED)
├── api.*          # PostgREST views (ENHANCED)
└── targeting.*    # Targeting-specific tables (existing)
```

## Enhanced Entities

### 1. meta.data_sources (Enhanced)

**Purpose**: Extended data source registry with semantic metadata for AI retrieval.

**Existing Fields** (preserved):
| Field | Type | Description |
|-------|------|-------------|
| source_id | SERIAL | Primary key |
| source_name | VARCHAR(100) | Unique source identifier |
| source_type | VARCHAR(50) | Type: 'api', 'file', 'scrape' |
| source_url | VARCHAR(500) | Source endpoint/location |
| description | TEXT | Human-readable description |
| refresh_frequency | VARCHAR(50) | 'daily', 'weekly', 'monthly', etc. |
| last_successful_refresh | TIMESTAMP | Last successful data pull |
| last_refresh_attempt | TIMESTAMP | Last attempted pull |
| last_refresh_status | VARCHAR(20) | 'success', 'failure', 'partial' |
| record_count | INTEGER | Current row count |
| is_active | BOOLEAN | Active/inactive flag |
| created_at | TIMESTAMP | Record creation time |

**New Fields** (added):
| Field | Type | Description |
|-------|------|-------------|
| topic_tags | TEXT[] | Categories for filtering: ['cms', 'hospital', 'financial'] |
| column_descriptions | JSONB | Column-level metadata for AI |
| staleness_threshold_hours | INTEGER | Hours before data is considered stale |
| table_size_bytes | BIGINT | Storage size for monitoring |
| ai_description | TEXT | LLM-friendly description for retrieval |
| target_tables | TEXT[] | Downstream tables this source populates |

**Column Descriptions JSONB Structure**:
```json
{
  "provider_id": {
    "description": "CMS 6-digit provider identification number",
    "type": "string",
    "examples": ["010001", "050001"],
    "nullable": false
  },
  "total_discharges": {
    "description": "Number of Medicare fee-for-service discharges",
    "type": "integer",
    "range": "1-50000",
    "nullable": false
  }
}
```

### 2. meta.table_health (New)

**Purpose**: Track health status of tables based on freshness and data quality metrics.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| health_id | SERIAL | PRIMARY KEY | Unique identifier |
| source_id | INTEGER | FK → data_sources | Source being tracked |
| check_timestamp | TIMESTAMP | DEFAULT NOW() | When check was performed |
| health_status | VARCHAR(20) | NOT NULL | 'healthy', 'stale', 'unhealthy' |
| freshness_hours | INTEGER | | Hours since last refresh |
| null_rate | DECIMAL(5,4) | | Percentage of null values (0.0000-1.0000) |
| validation_error_count | INTEGER | DEFAULT 0 | Number of validation failures |
| row_count | INTEGER | | Current row count |
| row_count_change | INTEGER | | Change from previous check |
| details | JSONB | | Additional health metrics |

**Health Status Rules**:
- `healthy`: freshness_hours ≤ threshold AND null_rate < 0.10 AND validation_error_count = 0
- `stale`: freshness_hours > threshold OR null_rate ≥ 0.10 (but not critical)
- `unhealthy`: freshness_hours > threshold × 2 OR validation_error_count > 100

### 3. meta.batch_jobs (New)

**Purpose**: Track batch job definitions and execution status.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| job_id | SERIAL | PRIMARY KEY | Unique identifier |
| job_name | VARCHAR(100) | UNIQUE, NOT NULL | Job identifier (e.g., 'fetch-cms-all') |
| description | TEXT | | Human-readable description |
| cron_schedule | VARCHAR(50) | | Cron expression (e.g., '0 2 * * 0') |
| source_ids | INTEGER[] | | Sources this job fetches |
| is_enabled | BOOLEAN | DEFAULT TRUE | Job enabled/disabled |
| last_run_at | TIMESTAMP | | Last execution time |
| last_run_status | VARCHAR(20) | | 'success', 'failure', 'running' |
| last_run_duration_seconds | INTEGER | | Execution duration |
| next_scheduled_run | TIMESTAMP | | Next planned execution |
| created_at | TIMESTAMP | DEFAULT NOW() | Job definition created |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last modified |

### 4. meta.batch_job_runs (New)

**Purpose**: Detailed execution history for batch jobs.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| run_id | SERIAL | PRIMARY KEY | Unique identifier |
| job_id | INTEGER | FK → batch_jobs | Parent job |
| triggered_by | VARCHAR(50) | NOT NULL | 'schedule', 'manual', 'api' |
| triggered_by_user | VARCHAR(100) | | User who triggered (if manual) |
| started_at | TIMESTAMP | NOT NULL | Execution start |
| completed_at | TIMESTAMP | | Execution end |
| status | VARCHAR(20) | NOT NULL | 'running', 'success', 'failure' |
| records_processed | INTEGER | | Total records handled |
| error_message | TEXT | | Error details if failed |
| k8s_job_name | VARCHAR(255) | | Kubernetes Job name |

## API Views (Enhanced)

### api.catalog (New)

**Purpose**: Expose data catalog for AI retrieval and monitoring dashboards.

```sql
CREATE OR REPLACE VIEW api.catalog AS
SELECT
    ds.source_id,
    ds.source_name,
    ds.source_type,
    ds.description,
    ds.ai_description,
    ds.topic_tags,
    ds.column_descriptions,
    ds.refresh_frequency,
    ds.last_successful_refresh,
    ds.record_count,
    ds.table_size_bytes,
    th.health_status,
    th.freshness_hours,
    th.null_rate,
    th.validation_error_count,
    th.check_timestamp AS health_checked_at,
    CASE
        WHEN th.health_status = 'healthy' THEN 'green'
        WHEN th.health_status = 'stale' THEN 'yellow'
        ELSE 'red'
    END AS status_color
FROM meta.data_sources ds
LEFT JOIN LATERAL (
    SELECT *
    FROM meta.table_health
    WHERE source_id = ds.source_id
    ORDER BY check_timestamp DESC
    LIMIT 1
) th ON TRUE
WHERE ds.is_active = TRUE;
```

**Filterable Fields** (via PostgREST query params):
- `topic_tags=cs.{cms}` - Contains tag 'cms'
- `health_status=eq.healthy` - Only healthy tables
- `source_type=eq.api` - Only API sources

### api.jobs (New)

**Purpose**: Expose batch job status and history.

```sql
CREATE OR REPLACE VIEW api.jobs AS
SELECT
    bj.job_id,
    bj.job_name,
    bj.description,
    bj.cron_schedule,
    bj.is_enabled,
    bj.last_run_at,
    bj.last_run_status,
    bj.last_run_duration_seconds,
    bj.next_scheduled_run,
    ARRAY_AGG(ds.source_name) AS source_names
FROM meta.batch_jobs bj
LEFT JOIN meta.data_sources ds ON ds.source_id = ANY(bj.source_ids)
GROUP BY bj.job_id;
```

### api.job_runs (New)

**Purpose**: Expose batch job execution history.

```sql
CREATE OR REPLACE VIEW api.job_runs AS
SELECT
    bjr.run_id,
    bj.job_name,
    bjr.triggered_by,
    bjr.triggered_by_user,
    bjr.started_at,
    bjr.completed_at,
    bjr.status,
    bjr.records_processed,
    bjr.error_message,
    EXTRACT(EPOCH FROM (bjr.completed_at - bjr.started_at)) AS duration_seconds
FROM meta.batch_job_runs bjr
JOIN meta.batch_jobs bj ON bjr.job_id = bj.job_id
ORDER BY bjr.started_at DESC;
```

## Entity Relationships

```
meta.data_sources (1) ──────< (N) meta.table_health
         │
         │ source_ids[]
         ▼
meta.batch_jobs (1) ──────< (N) meta.batch_job_runs
```

## Indexes

```sql
-- Catalog performance
CREATE INDEX idx_data_sources_topic_tags ON meta.data_sources USING GIN(topic_tags);
CREATE INDEX idx_data_sources_active ON meta.data_sources(is_active) WHERE is_active = TRUE;

-- Health lookups
CREATE INDEX idx_table_health_source_timestamp ON meta.table_health(source_id, check_timestamp DESC);
CREATE INDEX idx_table_health_status ON meta.table_health(health_status);

-- Job tracking
CREATE INDEX idx_batch_job_runs_job_started ON meta.batch_job_runs(job_id, started_at DESC);
CREATE INDEX idx_batch_job_runs_status ON meta.batch_job_runs(status) WHERE status = 'running';
```

## Data Quality Rules

### Validation Constraints

```sql
-- Health status must be valid
ALTER TABLE meta.table_health
ADD CONSTRAINT valid_health_status
CHECK (health_status IN ('healthy', 'stale', 'unhealthy'));

-- Null rate must be percentage
ALTER TABLE meta.table_health
ADD CONSTRAINT valid_null_rate
CHECK (null_rate >= 0 AND null_rate <= 1);

-- Job run status must be valid
ALTER TABLE meta.batch_job_runs
ADD CONSTRAINT valid_run_status
CHECK (status IN ('running', 'success', 'failure', 'cancelled'));
```

## Migration Notes

1. **Backward Compatibility**: All new fields on `meta.data_sources` have defaults
2. **Existing Data**: Run catalog refresh script after migration to populate new fields
3. **View Dependencies**: Drop and recreate `api.data_catalog` view (existing) after schema changes

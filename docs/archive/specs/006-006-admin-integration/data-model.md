# Data Model: Admin App Integration Fix

**Feature**: 006-006-admin-integration
**Date**: 2026-02-01

## Overview

This document defines the API view entities required for Admin App Compass integration. These views expose data from underlying tables (when available) or provide placeholder structure for development.

## Entities

### api.molecules

**Purpose**: Expose molecule discovery data for Compass search functionality.

**Source**: `mol_gold.molecules` (Feature 004) or placeholder

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NOT NULL | Unique molecule identifier |
| smiles | text | NOT NULL | Canonical SMILES representation |
| inchi_key | text | NULL | InChI key for structure identification |
| name | text | NULL | Common name or IUPAC name |
| molecular_weight | numeric | NULL | Molecular weight in g/mol |
| created_at | timestamptz | NOT NULL | Record creation timestamp |
| updated_at | timestamptz | NOT NULL | Last update timestamp |

**Constraints**:
- Exposes only active molecules (`is_active = true`)
- Read-only view (no INSERT/UPDATE/DELETE)

**Permissions**:
- web_anon: SELECT
- analyst: SELECT
- api_user: SELECT

**Placeholder Definition** (when underlying table doesn't exist):
```sql
CREATE OR REPLACE VIEW api.molecules AS
SELECT
  '00000000-0000-0000-0000-000000000000'::uuid AS id,
  'placeholder'::text AS smiles,
  'placeholder'::text AS inchi_key,
  'No molecules loaded'::text AS name,
  0::numeric AS molecular_weight,
  now() AS created_at,
  now() AS updated_at
WHERE false;
```

---

### api.resolution_queue

**Purpose**: Expose pending molecule resolution workflow items for Compass management.

**Source**: `mol_app.resolution_queue` (Feature 004) or placeholder

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NOT NULL | Resolution item identifier |
| source_id | text | NOT NULL | External source reference |
| target_smiles | text | NOT NULL | SMILES to resolve |
| status | text | NOT NULL | Workflow status |
| priority | integer | NOT NULL | Processing priority (higher = sooner) |
| created_at | timestamptz | NOT NULL | When item was queued |
| resolved_at | timestamptz | NULL | When resolution completed |

**Status Values**:
- `pending`: Awaiting processing
- `in_progress`: Currently being resolved
- `completed`: Successfully resolved (filtered out of view)
- `failed`: Resolution failed, needs review

**Constraints**:
- Excludes completed items (`status != 'completed'`)
- Read-only view

**Permissions**:
- web_anon: NO ACCESS (security requirement)
- analyst: SELECT
- api_user: SELECT

**Placeholder Definition**:
```sql
CREATE OR REPLACE VIEW api.resolution_queue AS
SELECT
  '00000000-0000-0000-0000-000000000000'::uuid AS id,
  'placeholder'::text AS source_id,
  'placeholder'::text AS target_smiles,
  'pending'::text AS status,
  0::integer AS priority,
  now() AS created_at,
  NULL::timestamptz AS resolved_at
WHERE false;
```

---

### api.data_sources (Enhanced)

**Purpose**: Expose data source metadata for Compass sources display.

**Source**: `mol_app.data_sources` or `meta.data_sources` or placeholder

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NOT NULL | Data source identifier |
| name | text | NOT NULL | Human-readable source name |
| source_type | text | NOT NULL | Type: 'chembl', 'pubchem', 'internal', etc. |
| last_fetch_at | timestamptz | NULL | Last successful data fetch |
| status | text | NOT NULL | Current status |
| record_count | bigint | NULL | Number of records from source |
| error_message | text | NULL | Last error if any |

**Status Values**:
- `active`: Source is operational
- `pending`: Awaiting first fetch
- `error`: Last fetch failed
- `disabled`: Manually disabled

**Permissions**:
- web_anon: SELECT
- analyst: SELECT
- api_user: SELECT

**Note**: This view already exists as placeholder. Will be updated when real data source table is available.

---

## Existing Views (Reference)

The following views already exist from Feature 005:

### api.health

| Column | Type | Description |
|--------|------|-------------|
| status | text | Always 'ok' |
| timestamp | timestamptz | Current timestamp |
| database | text | Database name |

### api.data_catalog

| Column | Type | Description |
|--------|------|-------------|
| schemaname | text | Schema name |
| tablename | text | Table name |
| row_count | bigint | Live tuple count |
| last_vacuum | timestamptz | Last vacuum time |
| last_analyze | timestamptz | Last analyze time |

### api.targets (Placeholder)

| Column | Type | Description |
|--------|------|-------------|
| hospital_id | text | Hospital identifier |
| name | text | Hospital name |
| tier | text | Targeting tier |
| score | numeric | Overall score |
| updated_at | timestamptz | Last update |

### api.scoring (Placeholder)

| Column | Type | Description |
|--------|------|-------------|
| hospital_id | text | Hospital identifier |
| factor | text | Scoring factor |
| weight | numeric | Factor weight |
| score | numeric | Factor score |

---

## Role Permission Matrix

| View | web_anon | analyst | api_user | readonly |
|------|----------|---------|----------|----------|
| api.health | SELECT | SELECT | SELECT | SELECT |
| api.data_catalog | SELECT | SELECT | SELECT | SELECT |
| api.molecules | SELECT | SELECT | SELECT | SELECT |
| api.data_sources | SELECT | SELECT | SELECT | SELECT |
| api.targets | - | SELECT | SELECT | SELECT |
| api.scoring | - | SELECT | SELECT | SELECT |
| api.resolution_queue | - | SELECT | SELECT | SELECT |

**Legend**: SELECT = read access, `-` = no access

---

## SQL Implementation

The view definitions are implemented in `k8s/base/db-init-job.yaml` as part of the database initialization process. See the implementation plan for the exact SQL with proper escaping.

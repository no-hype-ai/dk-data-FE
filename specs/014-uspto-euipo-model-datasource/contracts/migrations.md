# Contract: Database Migrations

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16

## 071_uspto_trademarks_raw.sql (NEW)

**File**: `src/dk_data/sql/migrations/071_uspto_trademarks_raw.sql`

### SQL

```sql
-- Migration: 071_uspto_trademarks_raw
-- Feature: 014-uspto-euipo-model-datasource
-- Purpose: Create raw table for USPTO TSDR trademark data

CREATE TABLE IF NOT EXISTS raw.uspto_trademarks (
    serial_number VARCHAR(20) NOT NULL,
    mark_element TEXT,
    mark_type VARCHAR(50),
    status VARCHAR(100),
    status_code INTEGER,
    status_date DATE,
    filing_date DATE,
    registration_number VARCHAR(20),
    registration_date DATE,
    nice_classes INTEGER[],
    us_classes TEXT[],
    owner_name TEXT,
    owner_entity_type VARCHAR(50),
    goods_and_services TEXT,
    description_of_mark TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (serial_number)
);

CREATE INDEX IF NOT EXISTS idx_uspto_tm_filing
    ON raw.uspto_trademarks(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_uspto_tm_nice
    ON raw.uspto_trademarks USING GIN(nice_classes);
CREATE INDEX IF NOT EXISTS idx_uspto_tm_status
    ON raw.uspto_trademarks(status);

DO $$
BEGIN
    RAISE NOTICE 'Migration 071_uspto_trademarks_raw complete.';
END
$$;
```

### Acceptance Criteria

- AC-1: Table created in `raw` schema with `serial_number` as unique key.
- AC-2: GIN index on `nice_classes` for Nice class filtering.
- AC-3: Follows existing migration naming convention (071_).

---

## 072_euipo_trademarks_raw.sql (NEW)

**File**: `src/dk_data/sql/migrations/072_euipo_trademarks_raw.sql`

### SQL

```sql
-- Migration: 072_euipo_trademarks_raw
-- Feature: 014-uspto-euipo-model-datasource
-- Purpose: Create raw table for EUIPO trademark data (TMview/IBM Gateway)

CREATE TABLE IF NOT EXISTS raw.euipo_trademarks (
    application_number VARCHAR(30) NOT NULL,
    mark_name TEXT,
    mark_kind VARCHAR(50),
    mark_feature VARCHAR(50),
    mark_basis VARCHAR(50),
    applicant_name TEXT,
    applicant_country VARCHAR(10),
    representative_name TEXT,
    status VARCHAR(100),
    filing_date DATE,
    registration_date DATE,
    expiry_date DATE,
    nice_classes INTEGER[],
    goods_and_services TEXT,
    image_url TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (application_number)
);

CREATE INDEX IF NOT EXISTS idx_euipo_tm_filing
    ON raw.euipo_trademarks(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_euipo_tm_nice
    ON raw.euipo_trademarks USING GIN(nice_classes);
CREATE INDEX IF NOT EXISTS idx_euipo_tm_status
    ON raw.euipo_trademarks(status);

DO $$
BEGIN
    RAISE NOTICE 'Migration 072_euipo_trademarks_raw complete.';
END
$$;
```

### Acceptance Criteria

- AC-1: Table created in `raw` schema with `application_number` as unique key.
- AC-2: GIN index on `nice_classes`.
- AC-3: EUIPO-specific fields (mark_kind, mark_feature, mark_basis, expiry_date, image_url) present.

---

## 073_trademark_status_history.sql (NEW)

**File**: `src/dk_data/sql/migrations/073_trademark_status_history.sql`

### SQL

```sql
-- Migration: 073_trademark_status_history
-- Feature: 014-uspto-euipo-model-datasource
-- Purpose: Track trademark status changes over time for both USPTO and EUIPO

CREATE TABLE IF NOT EXISTS raw.trademark_status_history (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    trademark_identifier VARCHAR(30) NOT NULL,
    source VARCHAR(20) NOT NULL CHECK (source IN ('uspto_trademarks', 'euipo_trademarks')),
    old_status VARCHAR(100),
    new_status VARCHAR(100) NOT NULL,
    change_detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_tm_history_identifier
    ON raw.trademark_status_history(trademark_identifier, source);
CREATE INDEX IF NOT EXISTS idx_tm_history_detected
    ON raw.trademark_status_history(change_detected_at DESC);

DO $$
BEGIN
    RAISE NOTICE 'Migration 073_trademark_status_history complete.';
END
$$;
```

### Acceptance Criteria

- AC-1: Table created in `raw` schema with UUID primary key.
- AC-2: CHECK constraint ensures source is valid.
- AC-3: Composite index on (trademark_identifier, source) for efficient lookups.
- AC-4: No foreign key constraints (raw layer is independent).

---

## seed_data_sources.sql (MODIFY)

**File**: `src/dk_data/sql/seed_data_sources.sql`

### Changes

Add after the `orcid` entry:

```sql
    -- Trademark data sources (014-uspto-euipo-model-datasource)
    ('uspto_trademarks', 'api', 'https://tsdrapi.uspto.gov/',
     'USPTO TSDR trademark case status data for pharmaceutical trademarks (Nice Class 5)', 'weekly', TRUE),

    ('euipo_trademarks', 'api', 'https://www.tmdn.org/tmview/api/search',
     'EUIPO trademark data via TMview federated search for pharmaceutical trademarks (Nice Class 5)', 'weekly', TRUE)
```

### Acceptance Criteria

- AC-1: Both trademark sources appear in `meta.data_sources` after seed.
- AC-2: `refresh_frequency` is 'weekly' for both.
- AC-3: Upsert (`ON CONFLICT`) handles re-runs.

# Contract: Gold SQLMesh Models

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16

## gold.molecule_profile (MODIFY — add IP trademark section)

**File**: `src/dk_data/sqlmesh/models/molecules/gold/molecule_profile.sql`

### Change Required

Add a new CTE `trademark_info` that aggregates trademark data from `silver.trademarks`, linked to molecules via `silver.molecule_aliases` (which contains brand names, trade names, and product names from DrugBank, FDA labels, and Orange Book). Uses case-insensitive equality matching on alias names — NOT substring matching on `canonical_name`, since trademarks are registered under brand names (e.g., "Humira"), not generic/INN names (e.g., "adalimumab"). Add 6 new columns to the final SELECT.

### New CTE

```sql
-- Trademark info (IP trademark section)
-- Links trademarks to molecules via molecule_aliases (brand/trade/product names)
-- Rationale: Trademarks are registered as brand names, not generic names.
-- silver.molecule_aliases already aggregates brand names from DrugBank, FDA labels,
-- Orange Book trade names, etc. — these are exactly what mark_name matches against.
trademark_info AS (
    SELECT
        ma.molecule_id,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) AS trademark_count,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) FILTER (
            WHERE t.status IN ('Registered', 'REGISTERED')
        ) AS active_trademark_count,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) FILTER (
            WHERE t.source = 'uspto_trademarks'
        ) AS us_trademark_count,
        COUNT(DISTINCT t.trademark_identifier || '|' || t.source) FILTER (
            WHERE t.source = 'euipo_trademarks'
        ) AS eu_trademark_count,
        (
            SELECT t2.status
            FROM silver.trademarks t2
            JOIN silver.molecule_aliases ma2
                ON LOWER(t2.mark_name) = LOWER(ma2.alias_name)
            WHERE ma2.molecule_id = ma.molecule_id
              AND t2.source = 'uspto_trademarks'
              AND ma2.alias_type IN ('brand', 'trade', 'product', 'canonical')
            ORDER BY t2.filing_date DESC NULLS LAST
            LIMIT 1
        ) AS latest_us_trademark_status,
        (
            SELECT t3.status
            FROM silver.trademarks t3
            JOIN silver.molecule_aliases ma3
                ON LOWER(t3.mark_name) = LOWER(ma3.alias_name)
            WHERE ma3.molecule_id = ma.molecule_id
              AND t3.source = 'euipo_trademarks'
              AND ma3.alias_type IN ('brand', 'trade', 'product', 'canonical')
            ORDER BY t3.filing_date DESC NULLS LAST
            LIMIT 1
        ) AS latest_eu_trademark_status
    FROM silver.molecule_aliases ma
    JOIN silver.trademarks t
        ON LOWER(t.mark_name) = LOWER(ma.alias_name)
    WHERE ma.alias_type IN ('brand', 'trade', 'product', 'canonical')
    GROUP BY ma.molecule_id
)
```

### New Columns in Final SELECT

```sql
    -- IP Trademark section (NEW)
    COALESCE(tm.trademark_count, 0) AS trademark_count,
    COALESCE(tm.active_trademark_count, 0) AS active_trademark_count,
    COALESCE(tm.us_trademark_count, 0) AS us_trademark_count,
    COALESCE(tm.eu_trademark_count, 0) AS eu_trademark_count,
    tm.latest_us_trademark_status,
    tm.latest_eu_trademark_status,
```

### New JOIN

```sql
LEFT JOIN trademark_info tm ON mb.molecule_id = tm.molecule_id
```

### Acceptance Criteria

- AC-1: `gold.molecule_profile` includes trademark counts for molecules with matching trademarks.
- AC-2: Molecules without trademarks have `trademark_count = 0` (COALESCE).
- AC-3: US and EU trademark counts are independent.
- AC-4: Latest status is per-registry (most recent by filing_date).
- AC-5: Existing columns are unchanged (no regression).
- AC-6: Linking uses `silver.molecule_aliases` (brand/trade/product/canonical names), NOT substring matching on `canonical_name`.
- AC-7: COUNT DISTINCT on `(trademark_identifier || '|' || source)` prevents double-counting when a molecule has multiple aliases matching the same trademark.

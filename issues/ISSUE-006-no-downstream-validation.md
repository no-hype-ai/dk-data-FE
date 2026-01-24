# ISSUE-006: No Data Validation on Downstream Pipeline Outputs

**Project**: dk-data-FE
**Category**: Data Quality & Reliability
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

While Pydantic validates data at ingestion, there's no validation that SQLMesh transformation outputs are correct. The `scoring.target_scores` table could contain NULL values, invalid tier classifications, or calculation errors if upstream transformations fail partially.

---

## Affected Files

| File | Stage | Validation |
|------|-------|------------|
| `src/dk_data/ingestion/utils/validators.py` | Ingestion | Pydantic models |
| `src/dk_data/sqlmesh/models/staging/*.sql` | Staging | None |
| `src/dk_data/sqlmesh/models/mart/*.sql` | Mart | None |
| `src/dk_data/sqlmesh/models/scoring/*.sql` | Scoring | None |
| `src/dk_data/sqlmesh/audits/data_quality.yaml` | Audits | Basic (likely incomplete) |

---

## Current Validation Coverage

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA PIPELINE                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INGESTION          STAGING           MART              SCORING             │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐        │
│  │ Pydantic │      │ SQLMesh  │      │ SQLMesh  │      │ SQLMesh  │        │
│  │ Validates│      │ Transforms│     │ Transforms│     │ Calculates│       │
│  │ ✅        │  →   │ ❌ No Val │  →   │ ❌ No Val │  →   │ ❌ No Val │        │
│  └──────────┘      └──────────┘      └──────────┘      └──────────┘        │
│                                                                              │
│  validated:        no validation:    no validation:    no validation:       │
│  - types           - NULLs ok        - bad joins       - wrong scores       │
│  - ranges          - bad transforms  - missing refs    - invalid tiers      │
│  - formats         - duplicates      - orphan records  - NULL components    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Evidence from Codebase

### SQLMesh Audit Configuration

```yaml
# sqlmesh/audits/data_quality.yaml
# (Contents not fully visible, likely basic checks)
```

**Issue**: SQLMesh audits exist but may not cover:
- Cross-table referential integrity
- Score calculation correctness
- Tier classification validity
- Null rate thresholds

### Scoring Table Schema (init_database.sql lines 224-241)

```sql
CREATE TABLE IF NOT EXISTS scoring.target_scores (
    score_id SERIAL PRIMARY KEY,
    hospital_key INTEGER NOT NULL REFERENCES mart.dim_hospital(hospital_key),
    score_date DATE NOT NULL,
    clinical_readiness_score INTEGER,      -- Can be NULL!
    operational_readiness_score INTEGER,   -- Can be NULL!
    strategic_alignment_score INTEGER,     -- Can be NULL!
    financial_capacity_score INTEGER,      -- Can be NULL!
    champion_access_score INTEGER,         -- Can be NULL!
    bonus_points INTEGER NOT NULL DEFAULT 0,
    penalty_points INTEGER NOT NULL DEFAULT 0,
    total_trs INTEGER NOT NULL,
    tier_classification CHAR(1) NOT NULL,
    data_completeness DECIMAL(5,4),
    CONSTRAINT valid_tier CHECK (tier_classification IN ('A', 'B', 'C', 'D', 'E'))
);
```

**Issues Identified**:
1. Sub-scores can be NULL but `total_trs` is NOT NULL - calculation could fail
2. No CHECK constraint on score ranges (0-100?)
3. `data_completeness` can be NULL
4. No constraint that `total_trs` = sum of sub-scores + bonus - penalty

---

## Failure Scenarios

### Scenario 1: Upstream NULL Propagation

```sql
-- If staging.hospitals has NULL bed_count
-- And mart.dim_hospital copies it
-- And scoring calculates: operational_score = bed_count / 10
-- Result: operational_readiness_score = NULL
-- But total_trs might still calculate (treating NULL as 0?)
```

### Scenario 2: Join Mismatch

```sql
-- mart.fact_tavr_program references hospital_key
-- If dim_hospital.hospital_key gets regenerated
-- Orphan records in fact_tavr_program
-- Scoring fails silently on missing join
```

### Scenario 3: Calculation Overflow

```sql
-- If bonus_points or penalty_points are extreme
-- total_trs could overflow INTEGER
-- Or become negative (no CHECK constraint)
```

---

## Recommended Solutions

### Phase 1: Add Database Constraints

#### 1.1 Score Range Constraints

```sql
-- migrations/003_add_score_constraints.sql
ALTER TABLE scoring.target_scores
ADD CONSTRAINT valid_clinical_score
    CHECK (clinical_readiness_score IS NULL OR
           (clinical_readiness_score >= 0 AND clinical_readiness_score <= 100));

ALTER TABLE scoring.target_scores
ADD CONSTRAINT valid_operational_score
    CHECK (operational_readiness_score IS NULL OR
           (operational_readiness_score >= 0 AND operational_readiness_score <= 100));

ALTER TABLE scoring.target_scores
ADD CONSTRAINT valid_strategic_score
    CHECK (strategic_alignment_score IS NULL OR
           (strategic_alignment_score >= 0 AND strategic_alignment_score <= 100));

ALTER TABLE scoring.target_scores
ADD CONSTRAINT valid_financial_score
    CHECK (financial_capacity_score IS NULL OR
           (financial_capacity_score >= 0 AND financial_capacity_score <= 100));

ALTER TABLE scoring.target_scores
ADD CONSTRAINT valid_champion_score
    CHECK (champion_access_score IS NULL OR
           (champion_access_score >= 0 AND champion_access_score <= 100));

ALTER TABLE scoring.target_scores
ADD CONSTRAINT valid_total_trs
    CHECK (total_trs >= 0 AND total_trs <= 500);

ALTER TABLE scoring.target_scores
ADD CONSTRAINT valid_data_completeness
    CHECK (data_completeness IS NULL OR
           (data_completeness >= 0 AND data_completeness <= 1));
```

#### 1.2 Referential Integrity Validation

```sql
-- Ensure all hospital_keys in scoring exist in mart
CREATE OR REPLACE FUNCTION validate_hospital_key()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM mart.dim_hospital
        WHERE hospital_key = NEW.hospital_key AND is_current = TRUE
    ) THEN
        RAISE EXCEPTION 'Invalid hospital_key: % not found in dim_hospital', NEW.hospital_key;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_scoring_hospital_key
BEFORE INSERT OR UPDATE ON scoring.target_scores
FOR EACH ROW EXECUTE FUNCTION validate_hospital_key();
```

### Phase 2: SQLMesh Audit Enhancements

#### 2.1 Comprehensive Audit Configuration

```yaml
# sqlmesh/audits/data_quality.yaml
audits:
  # Null checks for critical columns
  - name: staging_hospitals_no_null_ids
    model: staging.stg_hospitals
    query: |
      SELECT COUNT(*)
      FROM staging.stg_hospitals
      WHERE hospital_id IS NULL OR hospital_name IS NULL

  - name: mart_dim_hospital_no_orphans
    model: mart.dim_hospital
    query: |
      SELECT COUNT(*)
      FROM mart.dim_hospital d
      LEFT JOIN staging.stg_hospitals s ON d.hospital_id = s.hospital_id
      WHERE s.hospital_id IS NULL AND d.is_current = TRUE

  - name: scoring_no_null_totals
    model: scoring.target_scores
    query: |
      SELECT COUNT(*)
      FROM scoring.target_scores
      WHERE total_trs IS NULL

  - name: scoring_valid_tier_distribution
    model: scoring.target_scores
    query: |
      -- Alert if any tier has 0 hospitals (suspicious)
      SELECT COUNT(DISTINCT tier_classification)
      FROM scoring.target_scores
      WHERE score_date = (SELECT MAX(score_date) FROM scoring.target_scores)
      HAVING COUNT(DISTINCT tier_classification) < 5

  - name: scoring_total_matches_components
    model: scoring.target_scores
    description: "Verify total_trs equals sum of components"
    query: |
      SELECT COUNT(*)
      FROM scoring.target_scores
      WHERE total_trs != COALESCE(clinical_readiness_score, 0)
                       + COALESCE(operational_readiness_score, 0)
                       + COALESCE(strategic_alignment_score, 0)
                       + COALESCE(financial_capacity_score, 0)
                       + COALESCE(champion_access_score, 0)
                       + bonus_points
                       - penalty_points
```

### Phase 3: Post-Transformation Validation Script

#### 3.1 Python Validation Suite

```python
# scripts/validate_pipeline.py
"""Post-SQLMesh validation suite."""

import logging
from dataclasses import dataclass
from typing import List, Tuple

from ingestion.utils.database import get_cursor

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    check_name: str
    passed: bool
    message: str
    severity: str  # 'error', 'warning', 'info'

def run_validations() -> List[ValidationResult]:
    """Run all pipeline validations."""
    results = []

    with get_cursor() as cur:
        # Check 1: No NULL total_trs
        cur.execute("""
            SELECT COUNT(*) FROM scoring.target_scores
            WHERE total_trs IS NULL
        """)
        null_count = cur.fetchone()[0]
        results.append(ValidationResult(
            check_name="no_null_total_trs",
            passed=null_count == 0,
            message=f"Found {null_count} records with NULL total_trs",
            severity="error" if null_count > 0 else "info"
        ))

        # Check 2: Score component sum matches total
        cur.execute("""
            SELECT COUNT(*)
            FROM scoring.target_scores
            WHERE ABS(
                total_trs - (
                    COALESCE(clinical_readiness_score, 0) +
                    COALESCE(operational_readiness_score, 0) +
                    COALESCE(strategic_alignment_score, 0) +
                    COALESCE(financial_capacity_score, 0) +
                    COALESCE(champion_access_score, 0) +
                    bonus_points - penalty_points
                )
            ) > 1  -- Allow for rounding
        """)
        mismatch_count = cur.fetchone()[0]
        results.append(ValidationResult(
            check_name="score_sum_matches_total",
            passed=mismatch_count == 0,
            message=f"Found {mismatch_count} records where total != sum of components",
            severity="error" if mismatch_count > 0 else "info"
        ))

        # Check 3: Tier distribution is reasonable
        cur.execute("""
            SELECT tier_classification, COUNT(*) as cnt
            FROM scoring.target_scores
            WHERE score_date = (SELECT MAX(score_date) FROM scoring.target_scores)
            GROUP BY tier_classification
            ORDER BY tier_classification
        """)
        tier_dist = dict(cur.fetchall())
        all_tiers_present = all(t in tier_dist for t in ['A', 'B', 'C', 'D', 'E'])
        results.append(ValidationResult(
            check_name="all_tiers_represented",
            passed=all_tiers_present,
            message=f"Tier distribution: {tier_dist}",
            severity="warning" if not all_tiers_present else "info"
        ))

        # Check 4: No orphan hospital_keys in scoring
        cur.execute("""
            SELECT COUNT(*)
            FROM scoring.target_scores ts
            LEFT JOIN mart.dim_hospital dh ON ts.hospital_key = dh.hospital_key
            WHERE dh.hospital_key IS NULL
        """)
        orphan_count = cur.fetchone()[0]
        results.append(ValidationResult(
            check_name="no_orphan_hospital_keys",
            passed=orphan_count == 0,
            message=f"Found {orphan_count} scores referencing non-existent hospitals",
            severity="error" if orphan_count > 0 else "info"
        ))

        # Check 5: Data freshness in mart layer
        cur.execute("""
            SELECT
                'dim_hospital' as table_name,
                MAX(_updated_at) as last_update,
                COUNT(*) as record_count
            FROM mart.dim_hospital
            WHERE is_current = TRUE
            UNION ALL
            SELECT
                'fact_tavr_program',
                MAX(_updated_at),
                COUNT(*)
            FROM mart.fact_tavr_program
        """)
        for row in cur.fetchall():
            results.append(ValidationResult(
                check_name=f"mart_{row[0]}_populated",
                passed=row[2] > 0,
                message=f"{row[0]}: {row[2]} records, last update: {row[1]}",
                severity="error" if row[2] == 0 else "info"
            ))

    return results

def main():
    """Run validations and report results."""
    results = run_validations()

    errors = [r for r in results if r.severity == 'error' and not r.passed]
    warnings = [r for r in results if r.severity == 'warning' and not r.passed]

    print("\n" + "=" * 60)
    print("Pipeline Validation Report")
    print("=" * 60)

    for result in results:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"{status} [{result.severity.upper()}] {result.check_name}")
        print(f"    {result.message}")

    print("=" * 60)
    print(f"Total: {len(results)} checks, {len(errors)} errors, {len(warnings)} warnings")

    if errors:
        print("\n⛔ VALIDATION FAILED - Pipeline output is invalid")
        return 1
    elif warnings:
        print("\n⚠️  VALIDATION PASSED WITH WARNINGS")
        return 0
    else:
        print("\n✅ VALIDATION PASSED")
        return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
```

### Phase 4: Great Expectations Integration (Optional)

#### 4.1 Expectation Suite

```python
# expectations/scoring_suite.py
from great_expectations.core import ExpectationSuite
from great_expectations.expectations import (
    ExpectColumnValuesToNotBeNull,
    ExpectColumnValuesToBeBetween,
    ExpectColumnDistinctValuesToBeInSet,
)

suite = ExpectationSuite(
    expectation_suite_name="scoring_target_scores_suite",
    expectations=[
        ExpectColumnValuesToNotBeNull(column="total_trs"),
        ExpectColumnValuesToNotBeNull(column="tier_classification"),
        ExpectColumnValuesToBeBetween(
            column="total_trs",
            min_value=0,
            max_value=500
        ),
        ExpectColumnDistinctValuesToBeInSet(
            column="tier_classification",
            value_set=["A", "B", "C", "D", "E"]
        ),
        ExpectColumnValuesToBeBetween(
            column="data_completeness",
            min_value=0,
            max_value=1,
            mostly=0.95  # Allow 5% NULL
        ),
    ]
)
```

---

## Implementation Checklist

- [ ] Add CHECK constraints for score ranges
- [ ] Add trigger for hospital_key validation
- [ ] Enhance SQLMesh audits with comprehensive checks
- [ ] Create `validate_pipeline.py` script
- [ ] Add validation step to SQLMesh post-run hook
- [ ] Configure validation failures to block deployment
- [ ] Add validation metrics to monitoring dashboard
- [ ] Document expected data quality thresholds
- [ ] (Optional) Integrate Great Expectations

---

## Validation Triggers

| Event | Validation | Action on Failure |
|-------|------------|-------------------|
| After SQLMesh run | Full pipeline validation | Block API updates |
| Before scoring | Upstream completeness | Skip scoring if incomplete |
| Hourly | Data freshness | Alert if stale |
| On API request | Row count sanity | Return 503 if empty |

---

## References

- [SQLMesh: Audits](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/)
- [Great Expectations: Documentation](https://docs.greatexpectations.io/)
- [PostgreSQL: CHECK Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS)
- [dbt: Data Tests](https://docs.getdbt.com/docs/build/data-tests)

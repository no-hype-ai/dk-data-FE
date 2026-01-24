# ISSUE-018: No Defined Data Retention Policy

**Project**: dk-data-FE
**Category**: Compliance
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The platform lacks a formal data retention policy. Historical scores are retained indefinitely, `purge_history.py` exists but policy isn't documented, and there's no consideration for GDPR/CCPA if the platform expands to handle personal data.

---

## Current State

### Existing Retention Mechanism

From `purge_history.py` (lines 22-23):

```python
# Default retention period in days (2 years)
DEFAULT_RETENTION_DAYS = 730
```

**Issues**:
- Policy hardcoded in script, not documented
- Only applies to `scoring.score_history`
- No retention for other tables
- No archival strategy (data is deleted, not archived)

### Tables Without Retention

| Table | Growth Rate | Current Retention |
|-------|-------------|-------------------|
| raw.cms_medicare_inpatient | ~500K rows/year | Indefinite |
| raw.cms_hospital_info | ~6K rows/load | Indefinite |
| raw.acc_tvc_certification | ~500 rows/quarter | Indefinite |
| scoring.target_scores | ~6K rows/month | Indefinite |
| scoring.score_factors | ~30K rows/month | Indefinite |
| meta.refresh_log | ~100 rows/day | Indefinite |
| meta.batch_job_runs | ~50 rows/day | Indefinite |

---

## Storage Growth Projection

```
Year 1: ~500MB
Year 2: ~1.5GB
Year 3: ~3GB
Year 5: ~8GB
Year 10: ~20GB

Without retention:
- Storage costs increase linearly
- Query performance degrades
- Backup sizes grow continuously
- Compliance risk increases
```

---

## Regulatory Considerations

### HIPAA (Healthcare)

| Requirement | Implication |
|-------------|-------------|
| Retain 6 years from creation/last effective date | Minimum retention period |
| Secure disposal | Must document destruction |

### GDPR (if EU expansion)

| Requirement | Implication |
|-------------|-------------|
| Right to erasure | Must be able to delete on request |
| Data minimization | Don't keep longer than necessary |
| Purpose limitation | Delete when purpose fulfilled |

### CCPA (California)

| Requirement | Implication |
|-------------|-------------|
| Right to deletion | Must honor delete requests |
| Notice of retention | Must disclose retention periods |

### Industry Best Practices

| Data Type | Recommended Retention |
|-----------|----------------------|
| Transactional data | 7 years |
| Audit logs | 7 years |
| System logs | 90 days - 1 year |
| Analytics/metrics | 2-3 years |
| Temporary/cache | 30-90 days |

---

## Recommended Retention Policy

### Policy Matrix

| Schema | Table | Active Retention | Archive Retention | Total | Justification |
|--------|-------|------------------|-------------------|-------|---------------|
| raw | cms_* | 3 years | 4 years | 7 years | Source data for audit |
| staging | all | Latest only | None | N/A | Derived, can recreate |
| mart | dim_* | Indefinite | N/A | N/A | SCD history needed |
| mart | fact_* | 3 years | 4 years | 7 years | Business metrics |
| scoring | target_scores | 2 years | 5 years | 7 years | Decision history |
| scoring | score_factors | 1 year | 2 years | 3 years | Detail, can recreate |
| scoring | score_history | 2 years | 5 years | 7 years | Audit trail |
| meta | refresh_log | 1 year | 2 years | 3 years | Operational |
| meta | batch_job_runs | 1 year | 2 years | 3 years | Operational |
| audit | all | 2 years | 5 years | 7 years | Compliance |

---

## Implementation

### Phase 1: Policy Documentation

```markdown
# Data Retention Policy

**Effective Date**: 2026-01-15
**Version**: 1.0
**Owner**: Data Platform Team

## Retention Periods

### Active Data (PostgreSQL)
Data actively used for queries and analysis.

| Category | Retention | Example Tables |
|----------|-----------|----------------|
| Source Data | 3 years | raw.cms_* |
| Scoring | 2 years | scoring.target_scores |
| Operational | 1 year | meta.refresh_log |
| Audit | 2 years | audit.* |

### Archived Data (S3 Cold Storage)
Data retained for compliance but not actively queried.

| Category | Additional Retention | Total |
|----------|---------------------|-------|
| Source Data | +4 years | 7 years |
| Scoring | +5 years | 7 years |
| Audit | +5 years | 7 years |

## Deletion Process

1. Data older than active retention is archived monthly
2. Archived data older than total retention is deleted quarterly
3. All deletions are logged in audit.deletion_log
4. Legal hold overrides normal retention

## Exception Process

To request retention exception:
1. Document business justification
2. Get approval from Data Governance
3. Record exception in policy tracker
```

### Phase 2: Retention Tables

```sql
-- Retention configuration table
CREATE TABLE meta.retention_policy (
    policy_id SERIAL PRIMARY KEY,
    schema_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    active_retention_days INTEGER NOT NULL,
    archive_retention_days INTEGER DEFAULT 0,
    date_column VARCHAR(100) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    last_purge_at TIMESTAMPTZ,
    last_archive_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (schema_name, table_name)
);

-- Deletion audit log
CREATE TABLE audit.deletion_log (
    deletion_id SERIAL PRIMARY KEY,
    schema_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    deletion_type VARCHAR(20) NOT NULL,  -- 'purge', 'archive', 'manual'
    records_deleted INTEGER NOT NULL,
    date_range_start DATE,
    date_range_end DATE,
    deleted_by VARCHAR(100) NOT NULL,
    deleted_at TIMESTAMPTZ DEFAULT NOW(),
    reason TEXT
);

-- Legal hold table
CREATE TABLE meta.legal_holds (
    hold_id SERIAL PRIMARY KEY,
    hold_name VARCHAR(255) NOT NULL,
    schema_name VARCHAR(100),
    table_name VARCHAR(100),
    filter_condition TEXT,
    hold_start DATE NOT NULL,
    hold_end DATE,
    reason TEXT NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert retention policies
INSERT INTO meta.retention_policy
(schema_name, table_name, active_retention_days, archive_retention_days, date_column)
VALUES
('raw', 'cms_medicare_inpatient', 1095, 1460, '_loaded_at'),
('raw', 'cms_hospital_info', 1095, 1460, '_loaded_at'),
('raw', 'cms_cost_reports', 1095, 1460, '_loaded_at'),
('raw', 'acc_tvc_certification', 1095, 1460, '_loaded_at'),
('raw', 'hrsa_shortage_areas', 1095, 1460, '_loaded_at'),
('scoring', 'target_scores', 730, 1825, 'score_date'),
('scoring', 'score_factors', 365, 730, '_calculated_at'),
('scoring', 'score_history', 730, 1825, 'score_date'),
('meta', 'refresh_log', 365, 730, '_logged_at'),
('meta', 'batch_job_runs', 365, 730, 'started_at');
```

### Phase 3: Retention Automation

```python
#!/usr/bin/env python3
# scripts/apply_retention.py
"""Apply data retention policy."""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional

from ingestion.utils.database import get_connection, get_cursor

logger = logging.getLogger(__name__)

@dataclass
class RetentionPolicy:
    schema_name: str
    table_name: str
    active_retention_days: int
    archive_retention_days: int
    date_column: str

def get_policies() -> List[RetentionPolicy]:
    """Get all enabled retention policies."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT schema_name, table_name, active_retention_days,
                   archive_retention_days, date_column
            FROM meta.retention_policy
            WHERE is_enabled = TRUE
        """)
        return [RetentionPolicy(*row) for row in cur.fetchall()]

def check_legal_holds(schema: str, table: str) -> bool:
    """Check if table has active legal hold."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM meta.legal_holds
            WHERE is_active = TRUE
            AND hold_end IS NULL OR hold_end > CURRENT_DATE
            AND (
                (schema_name IS NULL AND table_name IS NULL)
                OR (schema_name = %s AND table_name IS NULL)
                OR (schema_name = %s AND table_name = %s)
            )
        """, (schema, schema, table))
        return cur.fetchone()[0] > 0

def archive_old_data(policy: RetentionPolicy, dry_run: bool = False) -> int:
    """Archive data older than active retention."""
    if check_legal_holds(policy.schema_name, policy.table_name):
        logger.info(f"Skipping {policy.schema_name}.{policy.table_name} - legal hold active")
        return 0

    cutoff_date = datetime.now() - timedelta(days=policy.active_retention_days)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Count records to archive
            cur.execute(f"""
                SELECT COUNT(*)
                FROM {policy.schema_name}.{policy.table_name}
                WHERE {policy.date_column} < %s
            """, (cutoff_date,))
            count = cur.fetchone()[0]

            if count == 0:
                return 0

            logger.info(f"{'[DRY RUN] ' if dry_run else ''}Archiving {count} records "
                       f"from {policy.schema_name}.{policy.table_name}")

            if dry_run:
                return count

            # In production, would export to S3 here
            # For now, just delete (should implement S3 export)

            cur.execute(f"""
                DELETE FROM {policy.schema_name}.{policy.table_name}
                WHERE {policy.date_column} < %s
            """, (cutoff_date,))

            # Log deletion
            cur.execute("""
                INSERT INTO audit.deletion_log
                (schema_name, table_name, deletion_type, records_deleted,
                 date_range_end, deleted_by, reason)
                VALUES (%s, %s, 'archive', %s, %s, 'retention_job', 'Retention policy')
            """, (policy.schema_name, policy.table_name, count, cutoff_date.date()))

            # Update policy last run
            cur.execute("""
                UPDATE meta.retention_policy
                SET last_archive_at = NOW()
                WHERE schema_name = %s AND table_name = %s
            """, (policy.schema_name, policy.table_name))

        conn.commit()

    return count

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Apply data retention policy')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    parser.add_argument('--table', help='Only process specific table')
    args = parser.parse_args()

    policies = get_policies()

    if args.table:
        policies = [p for p in policies if p.table_name == args.table]

    total_archived = 0
    for policy in policies:
        try:
            count = archive_old_data(policy, dry_run=args.dry_run)
            total_archived += count
        except Exception as e:
            logger.error(f"Error processing {policy.schema_name}.{policy.table_name}: {e}")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Total records archived: {total_archived}")

if __name__ == '__main__':
    main()
```

### Phase 4: CronJob for Retention

```yaml
# .gitops/base/retention/cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: data-retention
  namespace: tavr-data
spec:
  schedule: "0 3 1 * *"  # Monthly at 3 AM on 1st
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: retention
              image: tavr-job-trigger:latest
              command:
                - python
                - scripts/apply_retention.py
              env:
                - name: POSTGRES_HOST
                  value: postgres
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: postgres-secrets
                      key: password
          restartPolicy: OnFailure
```

---

## Implementation Checklist

- [ ] Document formal retention policy
- [ ] Create `meta.retention_policy` table
- [ ] Create `audit.deletion_log` table
- [ ] Create `meta.legal_holds` table
- [ ] Implement `apply_retention.py` script
- [ ] Add S3 archival before deletion
- [ ] Create retention CronJob
- [ ] Add retention dashboard
- [ ] Train team on legal hold process
- [ ] Schedule quarterly policy review

---

## References

- [HIPAA Retention Requirements](https://www.hhs.gov/hipaa/for-professionals/faq/580/how-long-should-records-be-retained/index.html)
- [GDPR Data Retention](https://gdpr.eu/article-17-right-to-be-forgotten/)
- [CCPA Compliance Guide](https://oag.ca.gov/privacy/ccpa)
- [PostgreSQL: Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)

# ISSUE-008: No Database Migration Strategy

**Project**: dk-data-FE
**Category**: Architecture
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The project lacks a database migration strategy. Schema changes require manual intervention through `init_database.sql`, with no version tracking, no rollback capability, and high risk of environment drift between dev/staging/prod.

---

## Affected Files

| File | Role | Issue |
|------|------|-------|
| `src/dk_data/sql/init_database.sql` | Initial schema | Monolithic, no versioning |
| `src/dk_data/sql/migrations/001_catalog_health_jobs.sql` | Migration file | Exists but no runner |
| `src/dk_data/Makefile` | Operations | No migration commands |

---

## Evidence from Codebase

### spec.md - Explicitly Out of Scope

```markdown
## Out of Scope
- Database migration automation (SQLMesh handles transformations, initial schema is manual).
```

**Issue**: SQLMesh handles *data* transformations but NOT schema migrations. These are different concerns.

### Current Schema Management

```bash
# From docker-compose.yml comments
# Initialize database after first start:
#   docker compose exec postgres psql -U postgres -d edwards_tavr -f /docker-entrypoint-initdb.d/init_database.sql
```

**Issues**:
1. `init_database.sql` is run manually
2. No idempotency guarantees
3. Re-running creates duplicate roles (errors)
4. No tracking of which migrations have been applied

### Existing Migration File

```
src/dk_data/sql/migrations/001_catalog_health_jobs.sql
```

**Issue**: Migration file exists but there's no migration runner to apply it.

---

## Risk Assessment

### Schema Drift Scenarios

```
Developer A                 Developer B                 Production
───────────────────────────────────────────────────────────────────
ALTER TABLE                     │                           │
 add column X                   │                           │
     │                          │                           │
     │                     ALTER TABLE                      │
     │                      add column Y                    │
     │                          │                           │
     └──────────────────────────┴───────────────────────────┘
                                │
                    Production has neither X nor Y
                    Deployment fails or data loss
```

### Current Risks

| Risk | Likelihood | Impact |
|------|------------|--------|
| Dev/Prod schema drift | High | Data loss on deploy |
| Rollback needed, no mechanism | Medium | Extended downtime |
| Team member applies wrong migration | Medium | Corrupted data |
| `init_database.sql` modification conflicts | High | Merge conflicts |

---

## Current vs Ideal State

### Current State

```
┌─────────────────┐
│init_database.sql│ ← 593 lines, monolithic
└────────┬────────┘
         │
         ▼ Manual execution
┌─────────────────┐
│  PostgreSQL     │
│  (no tracking)  │
└─────────────────┘
```

### Ideal State

```
┌─────────────────┐
│ migrations/     │
│  001_init.sql   │
│  002_roles.sql  │
│  003_catalog.sql│
│  ...            │
└────────┬────────┘
         │
         ▼ Automated runner
┌─────────────────┐
│ schema_versions │ ← Tracks applied migrations
│ PostgreSQL      │
└─────────────────┘
```

---

## Recommended Solutions

### Option A: Simple File-Based Migrations (Recommended)

#### A.1 Migration Table

```sql
-- Add to init_database.sql or as migration 000
CREATE TABLE IF NOT EXISTS meta.schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    checksum VARCHAR(64),
    execution_time_ms INTEGER,
    applied_by VARCHAR(255)
);
```

#### A.2 Migration Runner Script

```python
#!/usr/bin/env python3
# scripts/migrate.py
"""Database migration runner."""

import hashlib
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

import psycopg2

MIGRATIONS_DIR = Path(__file__).parent.parent / "sql" / "migrations"

def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        database=os.getenv("POSTGRES_DB", "edwards_tavr"),
    )

def get_applied_migrations(conn) -> set:
    """Get set of already-applied migration versions."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT version FROM meta.schema_migrations")
        return {row[0] for row in cur.fetchall()}
    except psycopg2.errors.UndefinedTable:
        # Migration table doesn't exist yet
        return set()
    finally:
        cur.close()

def get_pending_migrations() -> List[Tuple[str, Path]]:
    """Get list of pending migrations in order."""
    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = f.stem  # e.g., "001_initial_schema"
        migrations.append((version, f))
    return migrations

def calculate_checksum(filepath: Path) -> str:
    """Calculate MD5 checksum of migration file."""
    return hashlib.md5(filepath.read_bytes()).hexdigest()

def apply_migration(conn, version: str, filepath: Path, dry_run: bool = False):
    """Apply a single migration."""
    sql = filepath.read_text()
    checksum = calculate_checksum(filepath)

    print(f"{'[DRY RUN] ' if dry_run else ''}Applying: {version}")

    if dry_run:
        print(f"  Would execute {len(sql)} characters of SQL")
        return

    cur = conn.cursor()
    start_time = time.time()

    try:
        cur.execute(sql)
        execution_time_ms = int((time.time() - start_time) * 1000)

        cur.execute("""
            INSERT INTO meta.schema_migrations (version, checksum, execution_time_ms, applied_by)
            VALUES (%s, %s, %s, %s)
        """, (version, checksum, execution_time_ms, os.getenv("USER", "unknown")))

        conn.commit()
        print(f"  Applied in {execution_time_ms}ms")

    except Exception as e:
        conn.rollback()
        print(f"  FAILED: {e}")
        raise
    finally:
        cur.close()

def migrate(dry_run: bool = False, target_version: str = None):
    """Run pending migrations."""
    conn = get_connection()

    try:
        applied = get_applied_migrations(conn)
        pending = get_pending_migrations()

        # Filter to pending only
        to_apply = [
            (v, p) for v, p in pending
            if v not in applied and (target_version is None or v <= target_version)
        ]

        if not to_apply:
            print("No pending migrations.")
            return 0

        print(f"Found {len(to_apply)} pending migration(s):")
        for version, _ in to_apply:
            print(f"  - {version}")
        print()

        for version, filepath in to_apply:
            apply_migration(conn, version, filepath, dry_run=dry_run)

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Migration complete.")
        return 0

    except Exception as e:
        print(f"Migration failed: {e}")
        return 1

    finally:
        conn.close()

def status():
    """Show migration status."""
    conn = get_connection()

    try:
        applied = get_applied_migrations(conn)
        pending = get_pending_migrations()

        print("Applied migrations:")
        for version, _ in pending:
            if version in applied:
                print(f"  ✅ {version}")
            else:
                print(f"  ⏳ {version} (pending)")

    finally:
        conn.close()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database migration runner")
    parser.add_argument("command", choices=["migrate", "status", "dry-run"])
    parser.add_argument("--target", help="Target migration version")

    args = parser.parse_args()

    if args.command == "migrate":
        sys.exit(migrate(dry_run=False, target_version=args.target))
    elif args.command == "dry-run":
        sys.exit(migrate(dry_run=True, target_version=args.target))
    elif args.command == "status":
        status()
```

#### A.3 Split init_database.sql into Migrations

```bash
sql/migrations/
├── 000_create_migration_table.sql
├── 001_create_schemas.sql
├── 002_create_raw_tables.sql
├── 003_create_staging_tables.sql
├── 004_create_mart_tables.sql
├── 005_create_scoring_tables.sql
├── 006_create_meta_tables.sql
├── 007_create_api_views.sql
├── 008_create_roles.sql
├── 009_create_indexes.sql
└── 010_catalog_health_jobs.sql  # Existing migration
```

### Option B: Use Existing Tool (Alembic, Flyway, etc.)

#### B.1 Alembic Integration

```python
# alembic.ini
[alembic]
script_location = src/dk_data/alembic
sqlalchemy.url = postgresql://postgres:postgres@localhost:5433/edwards_tavr

# alembic/env.py
from alembic import context
from sqlalchemy import engine_from_config

def run_migrations_online():
    connectable = engine_from_config(...)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
```

#### B.2 Flyway Integration

```yaml
# docker-compose.yml
services:
  flyway:
    image: flyway/flyway:10
    command: migrate
    volumes:
      - ./sql/migrations:/flyway/sql
    environment:
      FLYWAY_URL: jdbc:postgresql://postgres:5432/edwards_tavr
      FLYWAY_USER: postgres
      FLYWAY_PASSWORD: ${POSTGRES_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
```

### Option C: PostgreSQL-Native (pg_dump/pg_restore)

For simpler deployments, use schema snapshots:

```bash
# Export current schema
pg_dump -h localhost -p 5433 -U postgres -d edwards_tavr --schema-only > schema_v1.sql

# Compare schemas
diff schema_v1.sql schema_v2.sql

# Apply diff
psql -h localhost -p 5433 -U postgres -d edwards_tavr < schema_diff.sql
```

---

## Makefile Integration

```makefile
# Database migrations
.PHONY: db-migrate db-migrate-dry db-status db-rollback

db-migrate:
	@echo "Running database migrations..."
	python scripts/migrate.py migrate

db-migrate-dry:
	@echo "Dry-run database migrations..."
	python scripts/migrate.py dry-run

db-status:
	@echo "Migration status..."
	python scripts/migrate.py status

db-rollback:
	@echo "Rollback not implemented - restore from backup"
	@exit 1
```

---

## GitOps Integration

```yaml
# .gitops/base/migrations/job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate
  annotations:
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      containers:
        - name: migrate
          image: tavr-job-trigger:latest
          command: ["python", "scripts/migrate.py", "migrate"]
          env:
            - name: POSTGRES_HOST
              value: postgres
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secrets
                  key: password
      restartPolicy: Never
```

---

## Implementation Checklist

- [ ] Create `meta.schema_migrations` table
- [ ] Implement `scripts/migrate.py` runner
- [ ] Split `init_database.sql` into numbered migrations
- [ ] Add migration commands to Makefile
- [ ] Add PreSync hook for GitOps deployments
- [ ] Document migration workflow in README
- [ ] Add CI check for migration file naming
- [ ] Create rollback procedure documentation

---

## Migration File Naming Convention

```
{NNN}_{description}.sql

Examples:
001_create_schemas.sql
002_create_raw_tables.sql
003_add_column_to_hospitals.sql
004_drop_deprecated_view.sql
```

- **NNN**: 3-digit sequence number
- **description**: Snake_case description of change
- Files are applied in lexicographic order

---

## References

- [Flyway: Database Migrations Made Easy](https://flywaydb.org/)
- [Alembic: Database Migration Tool](https://alembic.sqlalchemy.org/)
- [PostgreSQL: Schema Versioning Best Practices](https://wiki.postgresql.org/wiki/Change_management)
- [ArgoCD: Resource Hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/)

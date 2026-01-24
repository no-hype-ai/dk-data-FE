# ISSUE-009: SQLMesh Model Dependencies Not Explicit

**Project**: dk-data-FE
**Category**: Architecture
**Priority**: P2 - Medium
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

SQLMesh models have implicit dependencies through table references, but there's no explicit dependency graph validation. If `stg_hospitals` fails, downstream models like `dim_hospital` and `target_scores` may use stale data without warning. The `@daily` cron schedule may race with ingestion jobs.

---

## Affected Files

| File | Layer | Dependencies |
|------|-------|--------------|
| `sqlmesh/models/staging/stg_hospitals.sql` | Staging | raw.cms_hospital_info |
| `sqlmesh/models/mart/dim_hospital.sql` | Mart | staging.stg_hospitals |
| `sqlmesh/models/mart/fact_tavr_program.sql` | Mart | staging.stg_hospitals, staging.tavr_volumes |
| `sqlmesh/models/scoring/target_scores.sql` | Scoring | mart.dim_hospital, mart.fact_* |

---

## Current Pipeline Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SQLMESH PIPELINE                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  RAW TABLES          STAGING           MART              SCORING            │
│  (Ingestion)         (SQLMesh)         (SQLMesh)         (SQLMesh)          │
│                                                                              │
│  ┌──────────┐       ┌──────────┐      ┌──────────┐      ┌──────────┐       │
│  │cms_hosp_ │       │stg_      │      │dim_      │      │target_   │       │
│  │info      │──────▶│hospitals │─────▶│hospital  │─────▶│scores    │       │
│  └──────────┘       └──────────┘      └──────────┘      └──────────┘       │
│                                              │                  ▲           │
│  ┌──────────┐       ┌──────────┐      ┌─────┴────┐             │           │
│  │cms_      │       │stg_tavr_ │      │fact_tavr_│─────────────┘           │
│  │inpatient │──────▶│volumes   │─────▶│program   │                          │
│  └──────────┘       └──────────┘      └──────────┘                          │
│                                                                              │
│  ⏰ Ingestion       ⏰ @daily          ⏰ @daily          ⏰ @daily           │
│  06:00 UTC          08:00 UTC         08:00 UTC         08:00 UTC           │
│                                                                              │
│                     RACE CONDITION RISK                                      │
│                     Ingestion may not be complete when SQLMesh runs         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Evidence from Codebase

### sqlmesh/config.yaml (partial)

```yaml
model_defaults:
  dialect: postgres
  start: '2024-01-01'
```

**Issue**: No explicit dependency definitions or execution order constraints.

### Model Definitions (from ARCHITECTURE.md lines 291-310)

```sql
-- models/staging/stg_hospitals.sql
MODEL (
    name staging.stg_hospitals,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at
    ),
    cron '@daily'
);

SELECT
    provider_id,
    hospital_name,
    -- ...
FROM raw.cms_hospital_info
WHERE _loaded_at BETWEEN @start_dt AND @end_dt
```

**Issue**: Model relies on `_loaded_at` filter, but if ingestion hasn't completed, the query returns partial/no data.

---

## Failure Scenarios

### Scenario 1: Ingestion Overlaps with SQLMesh Run

```
Timeline:
06:00 - Ingestion CronJob starts
06:30 - Ingestion still running (large dataset)
08:00 - SQLMesh @daily kicks off
08:05 - stg_hospitals runs, sees incomplete raw data
08:10 - dim_hospital runs on stale staging
08:15 - target_scores runs on stale mart
08:30 - Ingestion completes
09:00 - API serves scores based on incomplete data
```

### Scenario 2: Staging Model Fails Silently

```
stg_hospitals fails (SQL syntax error after code change)
       │
       ▼
dim_hospital runs successfully (uses PREVIOUS stg_hospitals data)
       │
       ▼
target_scores calculates (on stale hospital data)
       │
       ▼
API serves outdated scores (no indication of staleness)
```

### Scenario 3: Partial Pipeline Success

```
Model Execution:
✅ stg_hospitals - success
✅ stg_tavr_volumes - success
✅ stg_certifications - success
❌ stg_geographic - FAILED (HRSA API was down)
✅ dim_hospital - runs (missing geographic data)
✅ fact_tavr_program - runs
✅ target_scores - calculates (with incomplete data)

Result: Scores missing shortage area factors
```

---

## Risk Assessment

| Issue | Likelihood | Impact |
|-------|------------|--------|
| Race condition with ingestion | High | Incomplete data in scores |
| Silent upstream failures | Medium | Stale/incorrect scores |
| Partial pipeline success | Medium | Missing score components |
| No dependency validation | Low | Unknown data lineage |

---

## Recommended Solutions

### Phase 1: Explicit DAG Definition

#### 1.1 Model Dependencies in SQLMesh

```sql
-- models/mart/dim_hospital.sql
MODEL (
    name mart.dim_hospital,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _updated_at
    ),
    cron '@daily',
    -- Explicit dependencies
    depends_on [staging.stg_hospitals, staging.stg_certifications]
);
```

#### 1.2 SQLMesh Configuration

```yaml
# sqlmesh/config.yaml
gateways:
  local:
    connection:
      type: postgres
      host: localhost
      port: 5433
      database: edwards_tavr
      user: postgres
      password: postgres

model_defaults:
  dialect: postgres
  start: '2024-01-01'

# DAG execution settings
plan:
  auto_apply: false  # Require manual apply after plan review

# Audits run after each model
audits:
  enabled: true
  fail_on_error: true  # Stop pipeline on audit failure
```

### Phase 2: Ingestion-SQLMesh Coordination

#### 2.1 Event-Driven Trigger

```python
# ingestion/batch/api.py
@app.post("/jobs/{job_name}/trigger")
async def trigger_job(job_name: str, user: str = None):
    # ... existing job trigger code ...

    # After all ingestion jobs complete, trigger SQLMesh
    if job_name == "fetch-all" and result.status == JobStatus.SUCCESS:
        # Trigger SQLMesh run via event
        await trigger_sqlmesh_pipeline()

async def trigger_sqlmesh_pipeline():
    """Trigger SQLMesh after successful ingestion."""
    runner = get_job_runner(DB_CONFIG)
    result = runner.run_job("sqlmesh-run", triggered_by="post-ingestion")
    logger.info(f"SQLMesh pipeline triggered: {result.status}")
```

#### 2.2 Completion Flag Pattern

```sql
-- meta.pipeline_state table
CREATE TABLE IF NOT EXISTS meta.pipeline_state (
    state_id SERIAL PRIMARY KEY,
    stage VARCHAR(50) NOT NULL,  -- 'ingestion', 'staging', 'mart', 'scoring'
    status VARCHAR(20) NOT NULL,  -- 'running', 'success', 'failed'
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    records_affected INTEGER,
    error_message TEXT
);

-- Check before SQLMesh run
SELECT status FROM meta.pipeline_state
WHERE stage = 'ingestion'
AND DATE(completed_at) = CURRENT_DATE
ORDER BY completed_at DESC
LIMIT 1;
```

### Phase 3: Upstream Validation Before Downstream

#### 3.1 Pre-Execution Checks

```sql
-- models/mart/dim_hospital.sql
MODEL (
    name mart.dim_hospital,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _updated_at
    ),
    cron '@daily',
    pre_statements [
        "SELECT CASE WHEN COUNT(*) = 0 THEN RAISE_EXCEPTION('stg_hospitals is empty') END FROM staging.stg_hospitals WHERE _updated_at > CURRENT_DATE - INTERVAL '2 days'"
    ]
);
```

#### 3.2 SQLMesh Audit for Freshness

```yaml
# sqlmesh/audits/data_quality.yaml
audits:
  - name: staging_hospitals_fresh
    model: staging.stg_hospitals
    query: |
      SELECT CASE
        WHEN MAX(_updated_at) < NOW() - INTERVAL '2 days'
        THEN 1 ELSE 0 END
      FROM staging.stg_hospitals

  - name: staging_data_complete
    model: staging.stg_hospitals
    query: |
      -- Fail if today's load has fewer than 80% of yesterday's records
      SELECT CASE
        WHEN today_count < yesterday_count * 0.8
        THEN 1 ELSE 0 END
      FROM (
        SELECT
          COUNT(*) FILTER (WHERE DATE(_updated_at) = CURRENT_DATE) as today_count,
          COUNT(*) FILTER (WHERE DATE(_updated_at) = CURRENT_DATE - 1) as yesterday_count
        FROM staging.stg_hospitals
      ) counts
```

### Phase 4: Pipeline Orchestration

#### 4.1 Kubernetes Job Dependency

```yaml
# .gitops/base/pipeline/job-sqlmesh.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: sqlmesh-run
spec:
  template:
    spec:
      initContainers:
        # Wait for ingestion to complete
        - name: wait-for-ingestion
          image: postgres:16-alpine
          command:
            - /bin/sh
            - -c
            - |
              until psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c \
                "SELECT 1 FROM meta.pipeline_state WHERE stage='ingestion' AND status='success' AND DATE(completed_at)=CURRENT_DATE" | grep -q 1; do
                echo "Waiting for ingestion to complete..."
                sleep 30
              done
      containers:
        - name: sqlmesh
          image: tavr-sqlmesh:latest
          command: ["sqlmesh", "run"]
```

#### 4.2 Airflow/Dagster Integration (Alternative)

```python
# dags/tavr_pipeline.py
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.sensors.sql import SqlSensor

with DAG('tavr_pipeline', schedule='@daily') as dag:

    wait_for_ingestion = SqlSensor(
        task_id='wait_for_ingestion',
        conn_id='postgres',
        sql="""
            SELECT 1 FROM meta.pipeline_state
            WHERE stage='ingestion' AND status='success'
            AND DATE(completed_at)=CURRENT_DATE
        """,
        timeout=3600,  # 1 hour
    )

    run_sqlmesh = BashOperator(
        task_id='run_sqlmesh',
        bash_command='sqlmesh run --gateway local',
    )

    validate_output = BashOperator(
        task_id='validate_output',
        bash_command='python scripts/validate_pipeline.py',
    )

    wait_for_ingestion >> run_sqlmesh >> validate_output
```

---

## Pipeline Execution Order

### Current (Implicit)

```
No guaranteed order - all models run when cron fires
```

### Recommended (Explicit)

```
1. Wait for ingestion completion flag
2. Run staging models (in parallel where possible)
   - stg_hospitals
   - stg_tavr_volumes
   - stg_certifications
   - stg_geographic
3. Run staging audits - STOP if any fail
4. Run mart models (respecting dependencies)
   - dim_hospital (depends on stg_hospitals, stg_certifications)
   - fact_tavr_program (depends on dim_hospital, stg_tavr_volumes)
   - fact_financial (depends on dim_hospital, stg_financial)
5. Run mart audits - STOP if any fail
6. Run scoring models
   - score_factors
   - target_scores
7. Run scoring audits - STOP if any fail
8. Update pipeline_state to 'success'
9. Trigger API cache refresh
```

---

## Implementation Checklist

- [ ] Add explicit `depends_on` to all SQLMesh models
- [ ] Create `meta.pipeline_state` table
- [ ] Add ingestion completion signal
- [ ] Create pre-execution freshness checks
- [ ] Add SQLMesh audits for data completeness
- [ ] Implement init container for dependency waiting
- [ ] Document expected execution order
- [ ] Add pipeline monitoring dashboard
- [ ] Configure alerts for pipeline failures

---

## References

- [SQLMesh: Model Dependencies](https://sqlmesh.readthedocs.io/en/stable/concepts/models/overview/#dependencies)
- [SQLMesh: Audits](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/)
- [Airflow: Task Dependencies](https://airflow.apache.org/docs/apache-airflow/stable/concepts/tasks.html)
- [Data Pipeline Best Practices](https://www.oreilly.com/library/view/data-pipelines-pocket/9781492087823/)

# ISSUE-005: Silent CronJob Failures and Data Freshness Drift

**Project**: dk-data-FE
**Category**: Data Quality & Reliability
**Priority**: P1 - High
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

Batch ingestion CronJobs can fail silently without alerting, leading to stale data in production. The `meta.data_catalog.health_status` depends on refresh scripts that may not run, creating a false sense of data freshness.

---

## Affected Files

| File | Issue |
|------|-------|
| `.gitops/base/ingestion/cronjob-cms-all.yaml` | No failure notifications |
| `.gitops/base/catalog/cronjob-refresh.yaml` | No alerting on health check failures |
| `src/dk_data/scripts/catalog_refresh.py` | Health status calculation depends on script running |
| `src/dk_data/sql/init_database.sql` | `staleness_threshold_hours` not enforced |

---

## Evidence from Codebase

### kustomization.yaml (lines 23-26)

```yaml
resources:
  # Batch Jobs (ingestion)
  - ingestion/cronjob-cms-all.yaml
  # Catalog refresh
  - catalog/cronjob-refresh.yaml
```

**Issue**: CronJobs exist but no monitoring or alerting is configured.

### init_database.sql - meta.data_sources (lines 287-288)

```sql
staleness_threshold_hours INTEGER DEFAULT 24,
```

**Issue**: The `staleness_threshold_hours` is stored but there's no automated system to:
1. Check if data exceeds the threshold
2. Alert when data becomes stale
3. Prevent stale data from being served via API

### Health Status Gap

```sql
-- meta.table_health stores health status
health_status VARCHAR(20) NOT NULL,  -- 'healthy', 'stale', 'unhealthy'

-- But this depends on catalog_refresh.py running successfully
-- If the refresh script fails, health status is never updated
```

---

## Failure Scenario Analysis

### Scenario 1: CronJob Pod Fails to Schedule

```
CronJob Schedule: 0 6 * * * (daily at 6 AM)
       │
       ▼
┌─────────────────┐
│ Kubernetes API  │
│ creates Job     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Pod Pending    │ ← Insufficient resources
│  (no CPU/mem)   │
└────────┬────────┘
         │
         ▼ After 6 hours...
┌─────────────────┐
│  Job Deadline   │
│   Exceeded      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SILENT FAIL    │ ← No notification sent
│  Data unchanged │
└─────────────────┘
```

### Scenario 2: API Ingestion Fails

```
┌─────────────────┐
│  CronJob runs   │
│  successfully   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fetcher runs   │
│  CMS API fails  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Exception logged│ ← Only to container stdout
│ to container    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ meta.refresh_log│
│ shows 'failed'  │ ← Nobody monitors this table
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SILENT FAIL    │ ← No alert, stale data served
└─────────────────┘
```

### Scenario 3: Catalog Refresh Never Runs

```
┌─────────────────┐
│ Data ingested   │
│  successfully   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ catalog_refresh │ ← This CronJob fails
│ CronJob fails   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ meta.table_health│
│ never updated   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ api.data_catalog│ ← Shows "fresh" for stale data
│ reports stale   │
│ data as fresh   │
└─────────────────┘
```

---

## Current Monitoring Gaps

| Component | Exists | Monitored | Alerted |
|-----------|--------|-----------|---------|
| CronJob schedule | Yes | No | No |
| Job completion | Yes | No | No |
| Fetcher success | Yes | No | No |
| Data freshness | Yes | No | No |
| Health status | Yes | No | No |

---

## Recommended Solutions

### Phase 1: CronJob Failure Detection

#### 1.1 Add Prometheus Metrics

```yaml
# .gitops/base/monitoring/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: cronjob-metrics
spec:
  endpoints:
    - port: metrics
  selector:
    matchLabels:
      app: kube-state-metrics
```

#### 1.2 Alert Rules for CronJob Failures

```yaml
# .gitops/base/monitoring/alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: cronjob-alerts
spec:
  groups:
    - name: cronjob-failures
      rules:
        - alert: CronJobFailed
          expr: |
            kube_job_status_failed{namespace="tavr-data"} > 0
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "CronJob {{ $labels.job_name }} failed"
            description: "CronJob has been failing for more than 5 minutes"

        - alert: CronJobNotScheduled
          expr: |
            time() - kube_cronjob_status_last_schedule_time{namespace="tavr-data"} > 86400 * 2
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "CronJob {{ $labels.cronjob }} hasn't run in 2 days"

        - alert: CronJobDeadlineExceeded
          expr: |
            kube_job_status_active{namespace="tavr-data"} > 0
            and
            time() - kube_job_status_start_time > 3600
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Job {{ $labels.job_name }} running for over 1 hour"
```

### Phase 2: Job Success Webhook

#### 2.1 Add Post-Job Notification

```yaml
# .gitops/base/ingestion/cronjob-cms-all.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: fetch-cms-all
spec:
  schedule: "0 6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: fetch-cms
              image: tavr-job-trigger:latest
              command:
                - /bin/sh
                - -c
                - |
                  python -m ingestion.fetch_data --source all
                  EXIT_CODE=$?

                  # Send notification on completion
                  if [ $EXIT_CODE -eq 0 ]; then
                    curl -X POST "$SLACK_WEBHOOK" \
                      -H 'Content-type: application/json' \
                      --data '{"text":":white_check_mark: CMS data fetch completed successfully"}'
                  else
                    curl -X POST "$SLACK_WEBHOOK" \
                      -H 'Content-type: application/json' \
                      --data "{\"text\":\":x: CMS data fetch FAILED with exit code $EXIT_CODE\"}"
                  fi

                  exit $EXIT_CODE
              env:
                - name: SLACK_WEBHOOK
                  valueFrom:
                    secretKeyRef:
                      name: alerting-secrets
                      key: slack-webhook
```

### Phase 3: Automated Staleness Detection

#### 3.1 SQL Function for Staleness Check

```sql
-- sql/catalog_functions.sql
CREATE OR REPLACE FUNCTION meta.check_data_staleness()
RETURNS TABLE (
    source_name VARCHAR,
    staleness_hours NUMERIC,
    threshold_hours INTEGER,
    is_stale BOOLEAN,
    health_status VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ds.source_name,
        EXTRACT(EPOCH FROM (NOW() - ds.last_successful_refresh)) / 3600 AS staleness_hours,
        ds.staleness_threshold_hours,
        EXTRACT(EPOCH FROM (NOW() - ds.last_successful_refresh)) / 3600 > ds.staleness_threshold_hours AS is_stale,
        CASE
            WHEN ds.last_successful_refresh IS NULL THEN 'unknown'
            WHEN EXTRACT(EPOCH FROM (NOW() - ds.last_successful_refresh)) / 3600 > ds.staleness_threshold_hours * 2 THEN 'unhealthy'
            WHEN EXTRACT(EPOCH FROM (NOW() - ds.last_successful_refresh)) / 3600 > ds.staleness_threshold_hours THEN 'stale'
            ELSE 'healthy'
        END AS health_status
    FROM meta.data_sources ds
    WHERE ds.is_active = TRUE;
END;
$$ LANGUAGE plpgsql;

-- View for API exposure
CREATE OR REPLACE VIEW api.health AS
SELECT
    'database' AS component,
    'healthy' AS status,
    NOW() AS checked_at
UNION ALL
SELECT
    source_name || '_freshness' AS component,
    health_status AS status,
    NOW() AS checked_at
FROM meta.check_data_staleness()
WHERE is_stale = TRUE;
```

#### 3.2 CronJob for Staleness Alerts

```yaml
# .gitops/base/catalog/cronjob-staleness-check.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: staleness-check
spec:
  schedule: "*/30 * * * *"  # Every 30 minutes
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: staleness-check
              image: postgres:16-alpine
              command:
                - /bin/sh
                - -c
                - |
                  STALE_SOURCES=$(psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -t -c "
                    SELECT string_agg(source_name || ' (' || ROUND(staleness_hours, 1) || 'h)', ', ')
                    FROM meta.check_data_staleness()
                    WHERE is_stale = TRUE
                  ")

                  if [ -n "$STALE_SOURCES" ]; then
                    curl -X POST "$SLACK_WEBHOOK" \
                      -H 'Content-type: application/json' \
                      --data "{\"text\":\":warning: Stale data sources detected: $STALE_SOURCES\"}"
                  fi
```

### Phase 4: Dashboard & Observability

#### 4.1 Grafana Dashboard JSON

```json
{
  "title": "TAVR Data Freshness",
  "panels": [
    {
      "title": "Data Source Staleness",
      "type": "table",
      "targets": [
        {
          "rawSql": "SELECT source_name, staleness_hours, threshold_hours, health_status FROM meta.check_data_staleness()",
          "format": "table"
        }
      ]
    },
    {
      "title": "CronJob Success Rate",
      "type": "stat",
      "targets": [
        {
          "expr": "sum(kube_job_status_succeeded{namespace='tavr-data'}) / sum(kube_job_status_succeeded{namespace='tavr-data'} + kube_job_status_failed{namespace='tavr-data'})"
        }
      ]
    }
  ]
}
```

#### 4.2 API Health Endpoint Enhancement

```python
# ingestion/batch/api.py
@app.get("/health/detailed")
async def detailed_health():
    """Detailed health check including data freshness."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Check database
    try:
        cursor.execute("SELECT 1")
        db_healthy = True
    except:
        db_healthy = False

    # Check data freshness
    cursor.execute("""
        SELECT source_name, staleness_hours, is_stale, health_status
        FROM meta.check_data_staleness()
    """)
    freshness = cursor.fetchall()

    cursor.close()
    conn.close()

    stale_sources = [s for s in freshness if s['is_stale']]

    return {
        "status": "healthy" if db_healthy and not stale_sources else "degraded",
        "database": "connected" if db_healthy else "disconnected",
        "data_freshness": {
            "total_sources": len(freshness),
            "stale_sources": len(stale_sources),
            "details": freshness,
        },
        "timestamp": datetime.now().isoformat(),
    }
```

---

## Implementation Checklist

- [ ] Create PrometheusRule for CronJob failure alerts
- [ ] Add Slack webhook notifications to CronJob templates
- [ ] Create `meta.check_data_staleness()` function
- [ ] Add staleness check CronJob (every 30 min)
- [ ] Create Grafana dashboard for data freshness
- [ ] Implement `/health/detailed` endpoint
- [ ] Add `api.health` view for PostgREST
- [ ] Configure AlertManager for routing
- [ ] Document on-call procedures for stale data alerts
- [ ] Set appropriate `staleness_threshold_hours` per source

---

## Recommended Staleness Thresholds

| Source | Refresh Frequency | Staleness Threshold |
|--------|-------------------|---------------------|
| cms_hospital_info | Monthly | 720 hours (30 days) |
| cms_medicare_inpatient | Quarterly | 2160 hours (90 days) |
| cms_cost_reports | Annual | 8760 hours (365 days) |
| acc_tvc | Quarterly | 2160 hours (90 days) |
| hrsa_shortage_areas | Monthly | 720 hours (30 days) |

---

## References

- [Kubernetes: CronJob Monitoring](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/#cron-job-limitations)
- [Prometheus: kube-state-metrics](https://github.com/kubernetes/kube-state-metrics)
- [AlertManager: Configuration](https://prometheus.io/docs/alerting/latest/configuration/)

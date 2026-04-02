# Data Model: Observability Dashboard & Metrics Fix

**Date**: 2026-04-02 | **Spec**: [spec.md](spec.md)

## Entities

This feature does not introduce new domain entities. It modifies the observability layer that monitors existing entities. The key data flows are:

### Existing: `meta.batch_job_runs` (extend usage)

Already exists in the database. Currently populated only by API-triggered jobs. Will be extended to also record scheduled CronJob executions.

| Field | Type | Purpose |
|-------|------|---------|
| `run_id` | SERIAL PK | Unique run identifier |
| `job_id` | INTEGER FK | References `meta.batch_jobs(job_id)` |
| `triggered_by` | VARCHAR(50) | `api`, `scheduler`, `backfill` |
| `started_at` | TIMESTAMP | Job start time |
| `completed_at` | TIMESTAMP | Job completion time |
| `status` | VARCHAR(20) | `running`, `success`, `failure`, `cancelled` |
| `records_processed` | INTEGER | Count of records processed |
| `error_message` | TEXT | Error details if failed |
| `k8s_job_name` | VARCHAR(255) | Kubernetes Job name |

**Change**: CronJob pods will INSERT into this table on completion (currently only API-triggered jobs do).

### Existing: `meta.batch_jobs` (read only)

| Field | Type | Purpose |
|-------|------|---------|
| `job_id` | SERIAL PK | Unique job identifier |
| `job_name` | VARCHAR(100) UNIQUE | CronJob name |
| `last_run_at` | TIMESTAMP | Most recent execution |
| `last_run_status` | VARCHAR(20) | Most recent result |
| `last_run_duration_seconds` | INTEGER | Duration of last run |

### Metric Taxonomy (75 defined, ~25 currently populated)

#### Gauges refreshed by `refresh_metrics_from_database_sync()` on each `/metrics` scrape

| Metric | Source Query | Currently Populated? |
|--------|-------------|---------------------|
| `dk_molecules_total` | `COUNT(*) FROM mol_silver.molecules` | Yes |
| `dk_clinical_trials_total` | `COUNT(*) FROM mol_silver.clinical_trials GROUP BY status` | Yes |
| `dk_adverse_events_reports_total` | `COUNT(*) FROM mol_bronze.faers_events + sider` | Yes |
| `dk_quarantine_count` | `COUNT(*) FROM mol_silver.molecules WHERE needs_review = TRUE` | Yes |
| `dk_entity_resolution_success_rate` | `resolved / total compounds` | Yes |
| `dk_data_source_last_refresh_timestamp` | Source-specific queries | Yes (22 sources) |
| `dk_data_source_row_count` | `COUNT(*)` per source table | Yes (23 sources) |
| `dk_gold_profiles_total` | `COUNT(*) FROM gold_molecule_profile` | Yes |
| `dk_silver_molecules_total` | `COUNT(*) FROM mol_silver.molecules` | Yes |
| `dk_resolution_queue_pending_total` | Hardcoded to 0 | Yes (but always 0) |
| `dk_data_source_table_size_bytes` | `pg_total_relation_size(table)` | **No — add** |
| `dk_data_source_staleness_hours` | `(NOW() - last_refresh) / 3600` | **No — add** |
| `dk_source_health_status` | Table existence + row count check | **Partial — extend** |
| `dk_layer_record_count` | `COUNT(*)` per schema (raw, bronze, silver, gold) | **No — add** |
| `dk_table_record_count` | `COUNT(*)` per individual table | **No — add** |
| `dk_raw_unprocessed_total` | `COUNT(*) WHERE processed_to_bronze = FALSE` | **No — add** |
| `dk_bronze_unprocessed_total` | `COUNT(*) WHERE processed_to_silver = FALSE` | **No — add** |
| `dk_silver_unprocessed_total` | Pending gold aggregation count | **No — add** |
| `dk_gold_unprocessed_total` | Pending downstream count | **No — add** |
| `dk_molecules_by_lifecycle_stage` | `COUNT(*) GROUP BY lifecycle_stage` | **No — add** |
| `dk_silver_identifier_mappings_total` | `COUNT(*) GROUP BY identifier_type` | **No — add** |

#### Counters/Histograms derived from `meta.batch_job_runs` (new refresh queries)

| Metric | Derivation | Currently Populated? |
|--------|-----------|---------------------|
| `batch_job_failures_total` | Already works for API-triggered | Yes (partial) |
| `batch_job_duration_seconds` | Already works for API-triggered | Yes (partial) |
| `batch_job_last_success_timestamp` | Already works for API-triggered | Yes (partial) |
| `dk_pipeline_records_processed_total` | `SUM(records_processed) FROM meta.batch_job_runs` | **No — add** |
| `dk_pipeline_duration_seconds` | From `completed_at - started_at` | **No — add** |
| `dk_pipeline_runs_total` | `COUNT(*) GROUP BY status` | **No — add** |
| `dk_pipeline_errors_total` | `COUNT(*) WHERE status = 'failure'` | **No — add** |

#### CMS-specific metrics (from agent execution data)

| Metric | Source | Currently Populated? |
|--------|--------|---------------------|
| `cms_source_health_status` | `record_cms_source_sync()` | Yes (27 sources) |
| `cms_records_ingested_total` | `record_cms_source_sync()` | Yes |
| `cms_fetch_duration_seconds` | `record_cms_fetch_duration()` | Yes |
| `cms_source_last_sync_timestamp` | `record_cms_source_sync()` | Yes |
| `cms_agent_executions_total` | `record_agent_run()` | **No — wire** |
| `cms_agent_records_enriched_total` | `record_agent_run()` | **No — wire** |
| `cms_agent_records_quarantined_total` | `record_agent_run()` | **No — wire** |
| `cms_agent_cost_usd` | `record_agent_run()` | **No — wire** |
| `cms_agent_last_run_status` | `record_agent_run()` | **No — wire** |
| `cms_gold_view_last_refresh_timestamp` | `record_gold_view_refresh()` | **No — wire** |
| `cms_gold_view_record_count` | `record_gold_view_refresh()` | **No — wire** |

## File Taxonomy (monitoring config)

### Current → Target

```
monitoring/                          → DELETE
├── dashboards/                      → grafana/dashboards/
│   ├── data-platform-overview.json  → fold into dk-data-platform-status.json
│   ├── pipeline-health.json         → fold into dk-data-transformations.json
│   ├── external-datasources.json    → fold into dk-data-pipeline-sources.json
│   ├── sqlmesh-transformations.json → fold into dk-data-transformations.json
│   ├── sqlmesh-lineage.json         → selected panels into dk-data-transformations.json
│   ├── cms-pipeline-health.json     → HOLD (blocked on #144)
│   ├── datasource-health.json       → fold into dk-data-pipeline-sources.json
│   ├── job-trigger-overview.json    → fold into dk-data-api-services.json
│   ├── postgrest-overview.json      → fold into dk-data-api-services.json
│   ├── dk-data-cronjobs.json        → fold into dk-data-platform-status.json
│   └── dk-data-overview.json        → fold into dk-data-platform-status.json
├── alerts/
│   ├── job-trigger.yaml             → merge into grafana/alerts/dk-data.yaml
│   ├── postgrest.yaml               → merge into grafana/alerts/dk-data.yaml
│   ├── cms-pipeline-source-failures.yaml → merge into grafana/alerts/dk-data.yaml
│   └── README.md                    → DELETE
└── provisioning/
    └── grafana-data-platform.yaml   → DELETE

k8s/apps/infrastructure/base/
├── alert-rules.yaml                 → DELETE (logic migrated to dk-data.yaml)
├── recording-rules.yaml             → DELETE (rules moved to Mimir ConfigMap in dk-alchemy)
└── service-monitor.yaml             → DELETE (scraping via pod annotations)

k8s/apps/metering-proxy/base/
└── servicemonitor.yaml              → DELETE
```

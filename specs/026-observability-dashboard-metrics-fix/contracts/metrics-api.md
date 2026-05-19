# Metrics API Contract

**Endpoint**: `GET /metrics`  
**Service**: job-trigger (FastAPI)  
**Consumer**: Alloy (Prometheus scraper, 30s interval)  
**Format**: Prometheus text exposition format (`text/plain; version=0.0.4`)

## Behavior

1. Alloy scrapes `GET /metrics` every 30 seconds
2. Before returning, the endpoint calls `refresh_metrics_from_database_sync()` to update all DB-backed gauges
3. Returns all registered Prometheus metrics from the `prometheus_client` default registry

## Response Time Budget

- Total: <2 seconds
- DB queries: <1.5 seconds (15 queries batched on single connection)
- Prometheus serialization: <200ms
- Network: <300ms

## Metric Categories Served

### HTTP Metrics (new — added by instrumentator)
```
http_requests_total{method="GET",path="/metrics",status="200"} 1234
http_request_duration_seconds_bucket{method="GET",path="/metrics",le="0.005"} 100
```

### Batch Job Metrics (existing + extended)
```
batch_job_failures_total{job_name="fetch-drugbank"} 0
batch_job_last_success_timestamp{job_name="fetch-drugbank"} 1.775142e+09
batch_job_duration_seconds_bucket{job_name="fetch-drugbank",le="60"} 5
```

### Data Source Freshness (existing + new DB queries)
```
dk_data_source_last_refresh_timestamp{source_id="1",source_name="drugbank"} 1.775063e+09
dk_data_source_row_count{source_id="1",source_name="drugbank"} 15234
dk_data_source_table_size_bytes{source_id="1",source_name="drugbank"} 52428800
dk_data_source_staleness_hours{source_id="1",source_name="drugbank"} 22.5
```

### Medallion Layer Backlogs (new DB queries)
```
dk_raw_unprocessed_total{source="drugbank"} 0
dk_bronze_unprocessed_total{source="drugbank"} 150
dk_layer_record_count{layer="raw"} 2500000
dk_layer_record_count{layer="bronze"} 1800000
dk_layer_record_count{layer="silver"} 950000
dk_layer_record_count{layer="gold"} 450000
```

### Platform Entity Gauges (existing + extended)
```
dk_molecules_total{status="published"} 12345
dk_quarantine_count 42
dk_entity_resolution_success_rate 0.97
dk_silver_identifier_mappings_total{identifier_type="chembl_id"} 8500
```

### Pipeline Event Metrics (new — derived from meta.batch_job_runs)
```
dk_pipeline_records_processed_total{layer="raw",source="drugbank"} 15000
dk_pipeline_runs_total{layer="bronze",source="all",status="success"} 28
dk_pipeline_duration_seconds_bucket{layer="bronze",source="all",le="300"} 25
```

### CMS Metrics (existing + agent metrics to wire)
```
cms_source_health_status{source="cms_part_d_spending"} 1
cms_agent_executions_total{agent_name="contact-verification"} 12
cms_agent_cost_usd{agent_name="contact-verification"} 0.45
```

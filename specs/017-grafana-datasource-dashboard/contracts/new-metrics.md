# New Metrics Contract

**Feature**: 017-grafana-datasource-dashboard

All four new metrics must be added to `src/dk_data/observability/metrics.py` before dashboard panels that depend on them will show data.

---

## `dk_data_source_table_size_bytes`

```python
DATA_SOURCE_TABLE_SIZE_BYTES = Gauge(
    "dk_data_source_table_size_bytes",
    "Storage size in bytes for data source table",
    ["source_id", "source_name"],
)
```

**Emit point**: `record_data_source_refresh()` — add `table_size_bytes: Optional[int] = None` parameter. When provided, call:
```python
DATA_SOURCE_TABLE_SIZE_BYTES.labels(
    source_id=source_id, source_name=source_name
).set(table_size_bytes)
```
Callers must fetch `meta.data_sources.table_size_bytes` before calling and pass it in.

---

## `dk_pipeline_duplicate_fetches_total`

```python
DK_PIPELINE_DUPLICATE_FETCHES = Counter(
    "dk_pipeline_duplicate_fetches_total",
    "Total fetch attempts skipped due to matching response_body_hash",
    ["source"],
)
```

**Emit point**: `src/dk_data/services/data_platform/raw_ingestion.py` — at the branch where a duplicate hash is detected (lines 196–201). Add:
```python
from dk_data.observability.metrics import DK_PIPELINE_DUPLICATE_FETCHES
DK_PIPELINE_DUPLICATE_FETCHES.labels(source=source_name).inc()
```

---

## `dk_silver_unprocessed_total`

```python
DK_SILVER_UNPROCESSED = Gauge(
    "dk_silver_unprocessed_total",
    "Unprocessed records in bronze layer pending silver transformation",
    ["source"],
)
```

**Emit point**: `src/dk_data/services/data_platform/metrics.py` — add `set_silver_unprocessed(source, count)` helper and call from `refresh_metrics_from_database_sync()`:
```python
def set_silver_unprocessed(source: str, count: int):
    """Set unprocessed record count in bronze layer pending silver."""
    if PROMETHEUS_AVAILABLE:
        DK_SILVER_UNPROCESSED.labels(source=source).set(count)
```
Query: `SELECT COUNT(*) FROM bronze.{table} WHERE processed_to_silver = FALSE`

---

## `dk_gold_unprocessed_total`

```python
DK_GOLD_UNPROCESSED = Gauge(
    "dk_gold_unprocessed_total",
    "Unprocessed records in silver layer pending gold aggregation",
    ["source"],
)
```

**Emit point**: `src/dk_data/services/data_platform/metrics.py` — add `set_gold_unprocessed(source, count)` helper:
```python
def set_gold_unprocessed(source: str, count: int):
    """Set silver record count pending gold aggregation."""
    if PROMETHEUS_AVAILABLE:
        DK_GOLD_UNPROCESSED.labels(source=source).set(count)
```
Query (primary): `SELECT COUNT(*) FROM silver.molecules WHERE needs_gold_aggregation = TRUE OR last_gold_sync IS NULL`
Query (fallback): `(SELECT COUNT(*) FROM silver.molecules) - (SELECT COUNT(*) FROM gold.molecule_profile)`

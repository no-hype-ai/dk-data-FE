# Tasks: Data Source Grafana Dashboard

**Input**: Design documents from `/specs/017-grafana-datasource-dashboard/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup (File Consolidation)

**Purpose**: Migrate orphaned dashboard files to canonical path and clean up dead directory tree. No code changes — pure file moves. Unblocks provisioning of all existing dashboards.

- [X] T001 Move 5 orphaned JSON files from `src/dk_data/monitoring/grafana/dashboards/` to `monitoring/dashboards/` (cms-pipeline-health.json, data-platform-overview.json, external-datasources.json, pipeline-health.json, sqlmesh-transformations.json)
- [X] T002 Delete now-empty directory tree `src/dk_data/monitoring/grafana/dashboards/` → `src/dk_data/monitoring/grafana/` → `src/dk_data/monitoring/` (rmdir each level if empty)

**Checkpoint**: `src/dk_data/monitoring/` no longer exists; 5 files visible under `monitoring/dashboards/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: New Prometheus metric definitions and recording rules CRD — must exist before any dashboard panel can reference them. Also scaffolds the new dashboard JSON.

**⚠️ CRITICAL**: Phases 3–6 all depend on this phase being complete.

- [X] T003 [P] Add `DATA_SOURCE_TABLE_SIZE_BYTES` Gauge (labels: `source_id`, `source_name`) to `src/dk_data/observability/metrics.py` alongside `DATA_SOURCE_ROW_COUNT` (line 120)
- [X] T004 [P] Add `DK_PIPELINE_DUPLICATE_FETCHES` Counter (label: `source`) to `src/dk_data/observability/metrics.py` alongside other pipeline counters
- [X] T005 [P] Add `DK_SILVER_UNPROCESSED` Gauge (label: `source`) to `src/dk_data/observability/metrics.py` alongside `DK_BRONZE_UNPROCESSED` (line 261)
- [X] T006 [P] Add `DK_GOLD_UNPROCESSED` Gauge (label: `source`) to `src/dk_data/observability/metrics.py` alongside `DK_SILVER_UNPROCESSED`
- [X] T007 [P] Emit `DATA_SOURCE_STALENESS_HOURS` in `src/dk_data/services/data_platform/metrics.py` — extend `refresh_metrics_from_database_sync()` to query `SELECT source_id, source_name, last_successful_refresh FROM meta.data_sources WHERE is_active = TRUE` and for each row call `DATA_SOURCE_STALENESS_HOURS.labels(source_id=str(row['source_id']), source_name=row['source_name']).set((now - row['last_successful_refresh']).total_seconds() / 3600)` (skip rows where `last_successful_refresh IS NULL`). **This is a blocker for T010 (freshness heatmap), T009 ($source variable), and all panel variable-scoping.** `DATA_SOURCE_STALENESS_HOURS` is defined at `observability/metrics.py:126` but currently has zero `.set()` calls in the entire codebase — confirmed by grep.
- [X] T008 Create `k8s/apps/infrastructure/base/recording-rules.yaml` using the contract at `specs/017-grafana-datasource-dashboard/contracts/recording-rules.yaml` (PrometheusRule CRD, 4 rules, 5m interval, limit: 200)
- [X] T009 Add `recording-rules.yaml` to the resources list in `k8s/apps/infrastructure/base/kustomization.yaml` (follow existing `alert-rules.yaml` pattern)
- [X] T010 Create `monitoring/dashboards/datasource-health.json` scaffold: `__metadata` wrapper (folder: "Data Platform", tags: ["dk-data","data-platform","datasource-health","auto-provisioned"], version: "1.0.0", maintainer: "data-platform-team"), `dashboard` object with uid, title, 8 empty row sections, two variables (`datasource` datasource-type, `source` query `label_values(dk_data_source_staleness_hours, source_name)`), `schemaVersion: 39`, `refresh: "5m"`, `time: {from: "now-24h", to: "now"}`

**Checkpoint**: `ruff check src/dk_data/observability/metrics.py` passes; `kubectl kustomize k8s/apps/infrastructure/base` renders without error; datasource-health.json is valid JSON.

---

## Phase 3: User Story 1 — Health at a Glance (Priority: P1) 🎯 MVP

**Goal**: Data-platform team can open the dashboard and immediately see which of the 26 sources are stale or erroring — without navigating to individual source pages.

**Independent Test**: Open datasource-health.json in Grafana. With `time=now-24h`, the Freshness Heatmap shows a 26-cell grid colored green/yellow/red from `dk_data_source_staleness_hours`. The Error Rate panel shows a bar chart sorted descending from `increase(dk_bronze_ingestion_errors_total[24h])` by `source` and `error_type`. Both panels degrade to "No data" (not zero) when the metric is absent.

### Implementation for User Story 1

- [X] T011 [US1] Add Row 1 "Freshness" to `monitoring/dashboards/datasource-health.json`: State timeline panel, query `dk_data_source_staleness_hours`, label `source_name`, thresholds green <4 / yellow 4–24 / red >24 (hours), `fieldConfig.defaults.noValue: "No data"`, `nullValueMode: "null"`, variable filter `{source_name=~"$source"}`. Depends on T007 (staleness emission) being deployed; without it the panel shows "No data".
- [X] T012 [US1] Add Row 4 "Error Rate" to `monitoring/dashboards/datasource-health.json`: Bar chart panel, query `increase(dk_bronze_ingestion_errors_total[24h])` grouped by `source` and `error_type`, sorted descending, `fieldConfig.defaults.noValue: "No data"`, `nullValueMode: "null"`, variable filter `{source=~"$source"}`

**Checkpoint**: Freshness heatmap and Error Rate panels render with real data on a 24h time range. Dashboard accessible only to `data-platform` Grafana team.

---

## Phase 4: User Story 2 — Pipeline Volume & Flow (Priority: P2)

**Goal**: Pipeline engineers can see ingestion throughput over time and visualise the medallion flow (raw → bronze → silver → gold) with per-layer backlog counts, enabling them to spot bottlenecks before SLA breaches.

**Independent Test**: Ingestion Volume stacked area chart shows per-source rates from `job:dk_pipeline_records_processed:rate5m` over a 30-day range without timeout. Sankey panel renders a 4-node flow diagram; silver/gold nodes show backlog counts once T015–T016 are deployed (shows "No data" gracefully before then).

### Implementation for User Story 2

- [X] T013 [P] [US2] Add `set_silver_unprocessed(source: str, count: int)` helper to `src/dk_data/services/data_platform/metrics.py`, setting `DK_SILVER_UNPROCESSED`; mirror the existing `set_bronze_unprocessed()` pattern
- [X] T014 [P] [US2] Add `set_gold_unprocessed(source: str, count: int)` helper to `src/dk_data/services/data_platform/metrics.py`, setting `DK_GOLD_UNPROCESSED`
- [X] T015 [US2] Extend `refresh_metrics_from_database_sync()` in `src/dk_data/services/data_platform/metrics.py` (line 208): add silver unprocessed query `SELECT COUNT(*) FROM bronze.{table} WHERE processed_to_silver = FALSE` per source (call `set_silver_unprocessed()`); add gold unprocessed query using `needs_gold_aggregation = TRUE OR last_gold_sync IS NULL` on `silver.molecules`, fallback to `silver COUNT(*) - gold.molecule_profile COUNT(*)` if column absent (call `set_gold_unprocessed()`)
- [X] T016 [US2] Add Row 2 "Ingestion Volume" to `monitoring/dashboards/datasource-health.json`: Stacked area chart, query `job:dk_pipeline_records_processed:rate5m` by `source`, `fieldConfig.defaults.noValue: "No data"`, variable filter `{source=~"$source"}`
- [X] T017 [US2] Add Row 6 "Medallion Flow" to `monitoring/dashboards/datasource-health.json`: `netsage-sankey-panel` v1.1.4 plugin panel (NOT volkovlabs-echarts-panel — discontinued Sept 2025); primary queries: `dk_raw_unprocessed_total`, `dk_bronze_unprocessed_total`, `dk_silver_unprocessed_total`, `dk_gold_unprocessed_total` (all filtered `{source=~"$source"}`); Transformations > Merge to produce 3-row table with columns `source`(text), `target`(text), `value`(number): rows `(raw, bronze, raw_value)`, `(bronze, silver, bronze_value)`, `(silver, gold, silver_value)`; fallback when silver/gold metrics absent: substitute `dk_layer_record_count{layer="silver"}` and `{layer="gold"}` — note these have no `source` label so the `$source` variable filter has no effect in fallback mode (acceptable degradation, add panel description noting "totals across all sources"); `fieldConfig.defaults.noValue: "No data"`

**Checkpoint**: Ingestion Volume panel loads in ≤5 seconds on 30-day range (uses recording rule). Sankey panel renders 4 nodes without plugin errors.

---

## Phase 5: User Story 3 — Fetch Performance & Duplicate Detection (Priority: P3)

**Goal**: Engineers can proactively detect API slowdowns (p50/p95 fetch duration trends) and identify sources wasting bandwidth re-fetching duplicate responses, before they cause pipeline failures or quota exhaustion.

**Independent Test**: Fetch Duration panel shows two time series (p50 and p95) from `job:dk_pipeline_duration_seconds_p50:5m` / `p95` per source over 30 days. Duplicate Detection panel shows `rate(dk_pipeline_duplicate_fetches_total[5m])` per source; returns "No data" gracefully if the counter has zero observations.

### Implementation for User Story 3

- [X] T018 [US3] Emit `DK_PIPELINE_DUPLICATE_FETCHES` in `src/dk_data/services/data_platform/raw_ingestion.py`: at the hash-match dedup branch (lines 196–201) import `DK_PIPELINE_DUPLICATE_FETCHES` from `src/dk_data/observability/metrics.py` and call `.labels(source=source_name).inc()` immediately after the duplicate is detected and insert is skipped
- [X] T019 [P] [US3] Add Row 3 "Fetch Duration" to `monitoring/dashboards/datasource-health.json`: Time series panel with two queries — `job:dk_pipeline_duration_seconds_p50:5m` and `job:dk_pipeline_duration_seconds_p95:5m` — both filtered `{source=~"$source"}`, unit `seconds`, `fieldConfig.defaults.noValue: "No data"`, `nullValueMode: "null"`
- [X] T020 [P] [US3] Add Row 5 "Duplicate Detection" to `monitoring/dashboards/datasource-health.json`: Time series panel, query `rate(dk_pipeline_duplicate_fetches_total[5m])` filtered `{source=~"$source"}`, unit `short` (ops/sec), `fieldConfig.defaults.noValue: "No data"`, `nullValueMode: "null"`

**Checkpoint**: After T018 is deployed and a duplicate fetch occurs, Duplicate Detection panel shows a non-zero rate. Fetch Duration panel loads 30-day data in ≤5 seconds.

---

## Phase 6: User Story 4 — Storage & Consumer Usage (Priority: P4)

**Goal**: Platform and infrastructure teams can track per-source storage growth (row count + bytes) for capacity planning, and see API consumer usage patterns (requests, response sizes, rate limit rejections) to manage quotas.

**Independent Test**: Storage Growth row count panel shows `dk_data_source_row_count` trends per source over 30 days. Storage bytes panel shows "No data" until T021 is deployed, then shows `job:dk_data_source_table_size_bytes:last` trends. API Consumer panels show `dk_data_metering_*` data (metering ServiceMonitor is already active).

### Implementation for User Story 4

- [X] T021 [US4] Extend `record_data_source_refresh()` in `src/dk_data/observability/metrics.py` (line 478): add optional parameter `table_size_bytes: Optional[int] = None`; when provided, call `DATA_SOURCE_TABLE_SIZE_BYTES.labels(source_id=source_id, source_name=source_name).set(table_size_bytes)`. Update call sites that already pass `source_id` and `source_name` to also pass `table_size_bytes` from `meta.data_sources.table_size_bytes` (query by `source_id`)
- [X] T022 [P] [US4] Add Row 7 "Storage Growth" to `monitoring/dashboards/datasource-health.json`: two Time series panels side by side — (a) row count: query `dk_data_source_row_count` filtered `{source_name=~"$source"}`, unit `short`; (b) bytes: query `job:dk_data_source_table_size_bytes:last` filtered `{source_name=~"$source"}`, unit `bytes`; both with `fieldConfig.defaults.noValue: "No data"`, `nullValueMode: "null"`
- [X] T023 [P] [US4] Add Row 8 "API Consumer Usage" to `monitoring/dashboards/datasource-health.json`: (a) Bar chart: `increase(dk_data_metering_requests_total[1h])` by `consumer` and `schema`, sorted descending; (b) Time series: `rate(dk_data_metering_response_bytes_total[5m])` by `consumer` and `schema`, unit `bytes/sec`; (c) Bar chart: `increase(dk_data_metering_rate_limit_rejections_total[1h])` by `consumer`, sorted descending; all with `fieldConfig.defaults.noValue: "No data"`, `nullValueMode: "null"`

**Checkpoint**: Row count panel shows data. Bytes panel shows data once T020 is deployed and an ingestion run completes. All 3 consumer panels render from existing metering metrics.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Access control, FR-012 compliance validation, schema validation, and final deployment verification.

- [X] T024 [P] Add Grafana provisioning folder config entry for `Data Platform` folder with `data-platform` team Viewer permission — file location depends on cluster's Grafana management method (Helm values `grafana.ini`, Grafana Operator CR `spec.config`, or provisioning YAML); check `.datakinetic/dk-data-prod.md` for the active Grafana deployment mechanism and add the folder entry there
- [X] T025 [P] Add `GF_INSTALL_PLUGINS: "netsage-sankey-panel"` (or `GF_PLUGINS_PREINSTALL`) to the Grafana deployment environment — same location as T024; note this requires a Grafana pod restart
- [X] T026 Audit all 11 panels in `monitoring/dashboards/datasource-health.json` for FR-012 compliance: every panel must have `fieldConfig.defaults.noValue: "No data"` and `nullValueMode: "null"` (or `"connected"` where appropriate) — fix any panels missing these fields
- [X] T027 Validate `monitoring/dashboards/datasource-health.json` against the existing dashboard schema by comparing structure against `monitoring/dashboards/dk-data-overview.json` — confirm `__metadata` wrapper, `dashboard` object, `schemaVersion`, panel `type` values, and variable definitions are all present and well-formed
- [X] T028 Run through `specs/017-grafana-datasource-dashboard/quickstart.md` checklist: verify Panel-by-Panel Data Readiness table matches actual metric availability; update any ✅/⏳ markers if implementation order changed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — **BLOCKS Phases 3–6**
- **User Story Phases (3–6)**: All depend on Phase 2 completion; can proceed in priority order or in parallel if staffed
- **Polish (Phase 7)**: Depends on all desired user story phases being complete

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational including T007 (staleness emission) — T011 (freshness panel) won't show data without it
- **US2 (P2)**: Depends only on Foundational — no dependency on US1/US3/US4
- **US3 (P3)**: Depends on Foundational (T003–T004 metric defs) — no dependency on US1/US2/US4
- **US4 (P4)**: Depends on Foundational (T003 metric def) — no dependency on US1/US2/US3

### Within Each User Story

- T003–T007 (metric defs + staleness emission): parallel — different functions/metric objects, all in `refresh_metrics_from_database_sync()` or `metrics.py` but non-conflicting
- T008–T009 (recording rules): T009 depends on T008 (file must exist before kustomization references it)
- T013–T014 (silver/gold helpers): parallel — different functions
- T015 (db queries): depends on T013 + T014 (helpers must exist)
- T019–T020 (fetch duration + duplicate panels): parallel — different row sections of same JSON
- T022–T023 (storage + consumer panels): parallel — different row sections of same JSON

### Parallel Opportunities

- T003, T004, T005, T006, T007 — 5 metric/emission tasks in parallel (different functions, same file but non-conflicting)
- T008 + T010 — recording-rules.yaml and dashboard scaffold are different files
- T013 + T014 — two helpers in same file, non-conflicting
- T019 + T020 — two dashboard panels in different row sections
- T022 + T023 — two dashboard rows in different sections
- T024 + T025 — Grafana folder config and plugin config (same location but independent config keys)
- T026 + T027 — audit and schema validation are read-only checks

---

## Parallel Example: Phase 2 Foundational

```bash
# These 5 metric/emission tasks can run in parallel (T003–T007):
Task: "Add DATA_SOURCE_TABLE_SIZE_BYTES to src/dk_data/observability/metrics.py"
Task: "Add DK_PIPELINE_DUPLICATE_FETCHES to src/dk_data/observability/metrics.py"
Task: "Add DK_SILVER_UNPROCESSED to src/dk_data/observability/metrics.py"
Task: "Add DK_GOLD_UNPROCESSED to src/dk_data/observability/metrics.py"
Task: "Emit DATA_SOURCE_STALENESS_HOURS in refresh_metrics_from_database_sync()"

# Simultaneously (different files):
Task: "Create k8s/apps/infrastructure/base/recording-rules.yaml"  # T008
Task: "Create monitoring/dashboards/datasource-health.json scaffold"  # T010
```

## Parallel Example: User Story 2

```bash
# These 2 helper tasks run in parallel (T013, T014):
Task: "Add set_silver_unprocessed() to src/dk_data/services/data_platform/metrics.py"
Task: "Add set_gold_unprocessed() to src/dk_data/services/data_platform/metrics.py"

# Then T015 (depends on both helpers completing):
Task: "Extend refresh_metrics_from_database_sync() with silver/gold queries"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (file migration — 5 minutes)
2. Complete Phase 2: Foundational (metric defs + recording rules + dashboard scaffold)
3. Complete Phase 3: User Story 1 (freshness heatmap + error rate)
4. **STOP and VALIDATE**: Open dashboard in Grafana, confirm both panels show live data
5. Deploy — dashboard is useful from this point

### Incremental Delivery

1. Setup + Foundational → Dashboard scaffold deployed, recording rules active
2. + US1 → Freshness and error visibility (immediate operational value)
3. + US2 → Pipeline volume and medallion flow (bottleneck visibility)
4. + US3 → Performance and duplicate tracking (cost/reliability visibility)
5. + US4 → Storage and consumer tracking (capacity planning visibility)

### Total Task Count

| Phase | Tasks | Parallelizable |
|---|---|---|
| Phase 1: Setup | 2 | 0 |
| Phase 2: Foundational | 8 | 6 (T003–T007, T008+T010) |
| Phase 3: US1 (P1) | 2 | 0 |
| Phase 4: US2 (P2) | 5 | 2 (T013+T014) |
| Phase 5: US3 (P3) | 3 | 2 (T019+T020) |
| Phase 6: US4 (P4) | 3 | 2 (T022+T023) |
| Phase 7: Polish | 5 | 4 (T024+T025, T026+T027) |
| **Total** | **28** | **16** |

---

## Notes

- [P] tasks = different files or independent additions — no merge conflicts expected
- No test tasks generated — tests not requested in spec.md (FR-012 compliance validated manually via T025)
- `netsage-sankey-panel` installation (T025) requires Grafana pod restart — coordinate with platform team
- T021 (table_size_bytes emit) requires knowing all call sites for `record_data_source_refresh()` — grep for callers before implementing
- Recording rules (T008–T009) take ~5 minutes to populate after `kubectl apply` — verify with `kubectl get prometheusrules` before assuming panel data is absent
- Gold unprocessed query (T015) column existence (`needs_gold_aggregation`) must be verified at implementation time — use fallback expression if column is absent
- T007 (staleness emission) is also added to `refresh_metrics_from_database_sync()` — coordinate with T015 to avoid write conflicts in the same function

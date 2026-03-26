# dk-data Platform Status Report — 2026-03-25

## Executive Summary

| Area                | Prod   | Staging |
|---------------------|--------|---------|
| Core Services       | YELLOW | YELLOW  |
| CronJobs            | GREEN  | RED     |
| Data Sources        | YELLOW | RED     |
| Observability       | RED    | RED     |
| SQLMesh Pipeline    | GREEN  | N/A     |
| Duplicate Detection | YELLOW | N/A     |

---

## Phase 1: Service Health

### Production (dk-data-prod)

| Service        | Expected             | Actual                        | Status |
|----------------|----------------------|-------------------------------|--------|
| PostgREST      | 3 replicas           | 3 Running + 1 stuck (old RS)  | YELLOW |
| Job Trigger    | 2 replicas           | 2 Running + 1 stuck (old RS)  | YELLOW |
| Metering Proxy | sidecar in PostgREST | NOT running on healthy pods   | RED    |

**Issues found:**

1. **PostgREST `5987bbf4c4-szcn7` — ImagePullBackOff:** Trying to pull `ghcr.io/data-kinetic/dk-data-fe:latest` (wrong image name/tag). This is an old ReplicaSet (1 desired) that failed to roll out. The image doesn't exist. Also violates Kyverno policies (non-approved registry for `postgrest/postgrest:v12.2.3`, `:latest` tag, missing init container resource limits).
2. **Job Trigger `59dbd59447-6968z` — CreateContainerConfigError:** container has `runAsNonRoot` and image has non-numeric user (`appuser`), cannot verify user is non-root. This is also a stuck old ReplicaSet trying to roll forward but failing on security context.
3. **Metering Proxy missing on healthy pods:** The 3 healthy PostgREST pods (`767d98bb44-*`) only have the `postgrest` container — no `metering-proxy` sidecar. The metering proxy only exists on the broken `5987bbf4c4` pod. This means prod has no API metering.
4. **External API returning 502:** `curl https://data.behaviorlabs.ai/health` returns `502 Bad Gateway`. The ingress routes to the `metering-proxy` service (port 3001), but `metering-proxy` is not running on any healthy pod. The 3 healthy PostgREST pods only expose port 3000.

### Staging (dk-data-staging)

| Service     | Expected   | Actual                         | Status |
|-------------|------------|--------------------------------|--------|
| PostgREST   | 2 replicas | 2 Running, 1/1 Ready           | GREEN  |
| Job Trigger | 1 replica  | 1 Running (1 restart 12h ago)  | GREEN  |

Staging health endpoint works: `https://data.staging.behaviorlabs.ai/health` returns OK.

---

## Phase 2: CronJobs & Data Sources

### Production — All 26 CronJobs running on schedule, none suspended

- **Daily fetchers (last 24h):** `journal-rss`, `news`, `openalex-ci`, `pubmed`, `sec-edgar` — all Succeeded
- **Weekly fetchers (last Sunday):** `ema-reg`, `hta`, `epo`, `euipo`, `orcid`, `pdb`, `uniprot`, `uspto-ci`, `patents`, `trademarks` — all Succeeded
- **Molecule pipeline:** `mol-fetch-daily`, `mol-transform`, `pg-backup-daily` — all Succeeded
- **Failed jobs:** `drugbank-seed` x2 — `BadZipFile: File is not a zip file` (corrupt/incomplete download)

### Staging — Multiple fetchers FAILING

| CronJob           | Status                     | Error                                        |
|-------------------|----------------------------|----------------------------------------------|
| fetch-news        | RED — 6 consecutive failures | `relation "raw.medical_news" does not exist` |
| fetch-openalex-ci | RED — 6 consecutive failures | `relation "raw.openalex_ci" does not exist`  |

**Root cause:** Staging database has ZERO raw tables. The `raw` schema exists but contains no tables. The `meta` schema only has `ops_schema_migrations` and `schema_migrations` — the actual `data_sources`, `batch_jobs`, etc. tables don't exist. Database migrations have not been run on staging.

### Production Data Freshness

The `meta.data_sources` table shows all sources have `last_successful_refresh = NULL` — the meta catalog is not being updated by the ingestion jobs. 4 sources show `status: failed` (`epo_ops`, `uspto_patents`, `euipo_trademarks`, `drugbank`).

**Raw table record counts (prod, populated):**

| Table               | Records   |
|---------------------|-----------|
| raw.openalex_ci     | 90,645    |
| raw.pubmed          | 5,450     |
| raw.journal_rss     | 720       |
| raw.medical_news    | 219       |
| raw.openfda_labels  | 38        |
| raw.clinicaltrials  | 37        |
| raw.chembl          | 5         |
| raw.pubchem         | 5         |
| raw.orcid           | 40        |
| 39 other tables     | 0 records |

---

## Phase 3: Duplicate Data Detection

| Table              | Total  | Duplicate Hashes             | Assessment |
|--------------------|--------|------------------------------|------------|
| raw.clinicaltrials | 37     | 6 duplicate hashes           | YELLOW     |
| raw.openfda_labels | 38     | 7 duplicate hashes           | YELLOW     |
| raw.openalex_ci    | 90,645 | No `response_body_hash` column | GAP      |
| raw.pubmed         | 5,450  | No `response_body_hash` column | GAP      |
| raw.journal_rss    | 720    | No `response_body_hash` column | GAP      |
| raw.medical_news   | 219    | No `response_body_hash` column | GAP      |

**Findings:**

- `clinicaltrials` and `openfda_labels` have duplicate response hashes — same data being re-ingested
- The 4 highest-volume tables (`openalex_ci`, `pubmed`, `journal_rss`, `medical_news`) do NOT have a `response_body_hash` column — no dedup capability at the raw layer
- The `BaseFetcher.calculate_hash()` method exists but is not consistently used across all fetchers
- No pre-fetch "should I download?" check exists — fetchers always download first, then check

---

## Phase 4: Observability

### Prometheus Metrics — PARTIALLY WORKING

- **ServiceMonitors:** `dk-data-job-trigger`, `dk-data-metering-proxy` — deployed
- **PodMonitors:** `dk-data-cronjobs`, `dk-data-molecule-cronjobs` — deployed
- **PrometheusRule:** `dk-data-alerts` — deployed
- **Job Trigger `/metrics` endpoint:** responding (Python 3.11.15)
- **Issue:** Metrics refresh error every ~10s: `relation "bronze.sider_adverse_reactions" does not exist` — a SQLMesh model references a table that doesn't exist yet

### Alloy/OTEL Traces — RED

- Alloy pods are Running (2 in `infra`, 2 in `infra-staging`)
- Alloy service exists: `10.43.42.176:4317` (ClusterIP)
- Port 4317 is **UNREACHABLE** from dk-data pods (both prod and staging)
- Alloy endpoints use host network IPs (`10.0.0.11`, `10.0.0.12`) not pod IPs — the DaemonSet runs in host network mode but the service selector may not match correctly
- Alloy logs show `err-mimir-sample-out-of-order` errors pushing to Mimir — duplicate scrape targets or clock skew
- All trace exports are failing with `StatusCode.UNAVAILABLE`

### Grafana — UP

- External endpoint: `https://grafana.behaviorlabs.ai/api/health` returns `{"database":"ok","version":"11.3.0"}`
- Dashboard JSON files exist in repo (`dk-data-overview.json`, `dk-data-cronjobs.json`)
- Whether dashboards are loaded into Grafana needs verification via the UI

### Structured Logging — WORKING

- Job Trigger produces JSON-formatted logs with trace context
- PostgREST produces standard format logs

---

## Phase 5: SQLMesh Pipeline (Prod)

CronJobs are running successfully:

- `mol-fetch-daily`: Last run 19h ago — Succeeded
- `mol-transform`: Last run 39h ago — Succeeded
- `mol-fetch-weekly`: Last run 3d18h ago — Succeeded

> Note: Cannot verify medallion layer record counts without querying `mol_*` schemas directly, but the pipeline CronJobs are completing without errors.

---

## Critical Action Items (Priority Order)

### P0 — Production API Down

1. **Fix prod 502:** The ingress routes to `metering-proxy` on port 3001, but healthy PostgREST pods don't have the `metering-proxy` sidecar. Either:
   - Scale down the old broken ReplicaSet (`5987bbf4c4`) and update the ingress/service to route directly to PostgREST port 3000, **OR**
   - Fix the metering-proxy deployment so it rolls out successfully (fix the `:latest` tag, add init container limits, use approved registry)

### P1 — Staging Completely Broken

2. **Run database migrations on staging:** Staging has zero `raw`/`meta` tables. All CronJob fetchers are failing. Run the migration scripts against the staging database.

### P1 — Observability Broken

3. **Fix Alloy OTLP connectivity:** Port 4317 unreachable from application pods. Likely a DaemonSet host networking issue — the service endpoints point to host IPs but pods can't reach them. Check Alloy's `hostNetwork` setting and ensure the service selector matches.
4. **Fix Mimir out-of-order samples:** Alloy is continuously erroring pushing to Mimir. Likely duplicate scrape targets from overlapping ServiceMonitors.

### P2 — Data Quality

5. **Fix `bronze.sider_adverse_reactions` missing table:** Job Trigger logs errors every 10s trying to query this table for metrics refresh.
6. **Fix DrugBank seed:** `BadZipFile` error — the XML file at `/app/data/drugbank/drugbank_all_full_database.xml.zip` is corrupt or truncated. Need to re-download.
7. **Clean up stuck ReplicaSets:** Delete the stuck `postgrest-5987bbf4c4` and `job-trigger-59dbd59447` pods/ReplicaSets.

### P3 — Dedup Gaps

8. **Add `response_body_hash` to high-volume raw tables:** `openalex_ci` (90K records), `pubmed` (5.4K), `journal_rss`, `medical_news` — none have dedup hash columns.
9. **Add pre-fetch hash check:** Currently all fetchers download data first, then check. Add a "last known hash" lookup before downloading to avoid re-fetching unchanged data.
10. **Investigate existing duplicates:** `clinicaltrials` (6 dup hashes/37 records) and `openfda_labels` (7 dup hashes/38 records) have significant duplication rates.

### P3 — Meta Catalog

11. **Fix `meta.data_sources` updates:** All sources show `last_successful_refresh = NULL` despite CronJobs running successfully. The completion reporting may not be updating the catalog correctly.

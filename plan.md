# dk-data-FE Robustness & Scale Plan

## Context

The prestaged hydration feature (spec 005) shipped five consecutive repair commits in one day (23cf83d → ad13d3a) and today triggered a cascading cluster incident: the hydration Job filled `k3s-master-1` ephemeral storage → node tainted `DiskPressure` → CNPG operator evicted → no Postgres primary → all writes blocked (issue #637). That pattern — a data-plane Job taking down the control plane that runs it — is the sharpest signal that today's architecture will not carry the system to *hundreds* of sources.

The next hydration window opens in ~24 hours. This plan commits three horizons (**Immediate / Near-term / Scale-ready**) for execution, aligns storage with `dk-alchemy`'s SeaweedFS, creates a CNPG disaster-recovery runbook instead of carving ArgoCD, picks an orchestrator that matches the sibling-repo pattern (plain k8s Jobs, no workflow engine), and opens a data-source roadmap built around free/accessible sources first with a templated onboarding pattern driven by the unified TypeScript CLI at `/Users/nick/Code/dk-cli`.

---

## Status snapshot — 2026-04-16

| Horizon | Item | Status | Reference |
|---|---|---|---|
| H1 | B.1 hardened hydrate Job manifest | ✅ | #303 (+ #317 tightening) |
| H1 | B.2 Job-level resilience | ✅ | #303 |
| H1 | B.3 Manifest row-count gate | ✅ | #305 |
| H1 | B.4 Zip extractor + Content-Length guard | ✅ | #307 |
| H1 | B.5 Missing alert rules | ✅ | #304 |
| H1 | B.6 CNPG deadlock runbook | ✅ | #300 |
| H1 | B.7 Lessons captured | ✅ | #301 |
| H1 | B.9 GH label taxonomy | ✅ | #299 + 46 labels created |
| H1 | B.10 Node labels verified | ✅ | labels live on cluster (master=control/nvme-hdd, slave=general/nvme-hdd); dk-alchemy #651 closed |
| H1 | B.11 Procurement issues | ✅ | #302 + issues #290–#298 |
| H2 | C.1 SeaweedFS client module | ✅ | #311 |
| H2 | C.2 Real WAL backpressure | ✅ | #315 (migration 231) |
| H2 | C.3 DLQ / source quarantine | ✅ | #316 (migration 232) |
| H2 | C.4 Download integrity pipeline | ✅ | #313 (migration 229) |
| H2 | C.5 PgBouncer pool split | ✅ | #310 |
| H2 | C.6 Observability metrics expansion | ✅ | #312 |
| H2 | C.7 SQLMesh audits at boundaries | ✅ | #314 |
| 005 | feature/005 prestaged hydration | ✅ | #309 (27-commit merge) |
| H3 | D.1 Dispatcher + per-source Jobs | ✅ | #322 |
| H3 | D.2 Source descriptors | ✅ | #318 (migration 233) |
| H3 | D.3 Admission control by budget | ✅ | #320 (migration 234) |
| H3 | D.4 Control-plane node taint | ⚠️ | #317 shipped; dk-alchemy #660 closed prematurely — REOPENED (taint not on cluster) |
| H3 | D.5 Per-source DopplerSecret CRs | ✅ | #321 + dk-alchemy #661 + sweep #319 |
| J.1 | Push-via-API dashboards in-repo | ✅ | #306 (6 renamed + 6 stubs) |
| J.2 | Grafana-operator migration | ⏸️ | deferred — dk-alchemy #647 |
| Part F | CLI extension in dk-cli | ✅ | dk-cli #1 ✅, #2 ✅ (shipped via dk-cli PR #4 Stage 1–4); #3 tracking open |
| Part E | Future-source stubs (~80) | ⏸️ | roadmap; priority:top15 labeled |

**Cross-repo issues** (snapshot 2026-04-16 08:40 CDT): dk-alchemy #646 ✅, #651 ✅, #656 ✅ (PR #665, ArgoCD sync pending), #661 ✅; #660 reopened (taint not applied); #647, #648, #649, #650, #659 still open. dk-cli #1/#2/#3 ✅ (PRs #4, #5, #6 shipped H1+H2+H3 CLI surface). dk-data-FE #319 ✅ via PR #323; #290–#298 T4 procurement still awaiting legal.

---

## Part A — Diagnosis summary

### A.1 The truncation question — answered

**There is no truncation inside `prestaged.py`.** When truncation happens, it's introduced upstream and nothing catches it. Three mechanisms:

1. **Zip extraction silently keeps only *one* file.** `src/dk_data/ingestion/downloaders/cms_downloader.py:520-536` sorts CSVs by size and extracts only the largest; everything else in the zip is dropped. NPPES ships multi-file zips (`npidata_*.csv`, `othername_*.csv`, `pl_*.csv`, `endpoint_*.csv`); under this logic, four files become one. Non-CSV files (TXT, XLSX, PSV) are not inspected at all. This is the most likely explanation for the "truncation" observation.
2. **Streamed downloads have no integrity guard.** `download_cms_file:503-518` only catches the zero-byte case. A partial download produces a short-but-nonempty CSV; the 30-day file-age cache (line 488) serves the stale short file for weeks. No `Content-Length`, ETag, or digest verification.
3. **Prestaged dumps are validated only by the 5-byte `PGDMP` magic header** (`prestaged.py:193-200`). A dump truncated in transit still starts with `PGDMP` and `pg_restore` loads whatever reached disk. Post-restore `COUNT(*)` is recorded (`prestaged.py:420-426`) but never compared against an expected value. The optional manifest at `src/dk_data/ingestion/prestaged_manifest.schema.json` was designed for this but never wired.

**Direct answer**: the zip contents were *not* inspected end-to-end — the downloader throws away everything except the single largest CSV before the zip leaves `/tmp/cms_downloads/`. The files you could "see" in the zip are not the files that reached Postgres.

### A.2 Top brittleness issues (ranked)

| # | Issue | Evidence | Severity |
|---|-------|----------|----------|
| 1 | Hydration Job can fill control-plane node and evict Postgres operator | Today's incident; `hostPath` on master | Critical |
| 2 | ArgoCD `selfHeal` keeps reconciling operator onto tainted node | Obs 2610; issue #637 | Critical |
| 3 | WAL throttle returns `0.0` — no backpressure (FR-007 unimplemented) | `wal_throttle.py:49-68` | High |
| 4 | Zip extraction keeps only largest CSV | `cms_downloader.py:520-536` | High |
| 5 | No row-count reconciliation vs source/manifest | `prestaged.py:420-426` | High |
| 6 | Downloads have no Content-Length / digest guard | `cms_downloader.py:503-518` | High |
| 7 | `backoffLimit: 0` + no retry = transient failure is fatal | All job manifests | High |
| 8 | `hostPath` PV pinned to single node | `prestaged-hydrate-pv-slave.yaml` | High |
| 9 | PgBouncer pool at ceiling, "no headroom" | `pgbouncer.yaml:41-50` | High |
| 10 | No liveness probe or DB precheck in hydrate pod | Base Job manifest | Medium |
| 11 | Monolithic serial Job — one bad source blocks all | Spec says "serial for v1" | Medium |
| 12 | Credentials in a single DopplerSecret for all sources | `dk-data-secrets` | Medium |
| 13 | `.dk/memory/lessons.md` is empty despite today's incidents | Read the file | Medium |

### A.3 Current-state reference

- **Sources wired**: 73 fetchers across mol (32), hcs (28 CMS), ip (7), hcp (2), ind (4), regulatory (7 incl. SEC EDGAR); 34 in `SOURCE_LOAD_ORDER`, rest run ad-hoc.
- **Orchestration**: monolithic serial `Job`, plus ~130 native `CronJob`s under `k8s/apps/cronjobs/base/` — per-source cronjobs are already the house style; the monolithic hydrate is the outlier.
- **Observability**: 6 Grafana dashboards, metrics in `src/dk_data/observability/metrics.py`, JSON+OTLP logs, PostgREST hydration dashboard — but no alerts for disk-fill, hydration failure, CNPG primary-absent, or row-count mismatch.
- **Storage**: `hostPath` on k3s-master/slave for prestaged dumps; `dk-alchemy` has migrated MinIO → SeaweedFS (endpoint `http://seaweedfs-s3.infra.svc.cluster.local:8333`, secret `seaweedfs-secret`, boto3 sig v4 path-style, S3 module named `minio_admin.py` *deliberately*). dk-data-FE has not yet aligned.
- **Sibling-repo stance on workflow engines**: *none deployed* in dk-alchemy (no Argo Workflows, Temporal, Prefect, Dagster, Airflow, KEDA). Batch work there is plain `CronJob`. ArgoCD is the only "argo" in the stack, and it's GitOps — not an engine.
- **Unified CLI**: `/Users/nick/Code/dk-cli` is a fresh repo (empty, only `README.md`, 8 bytes). TypeScript CLI at `/Users/nick/Code/dk-alchemy/src/dk-cli` (bun-based, `package.json` + `bun.lock`) is migrating into `/Users/nick/Code/dk-cli`. This becomes the home for `dk-data` subcommands too, driving one CLI for the whole platform.

---

## Part B — Horizon 1: Immediate (next 24 hours, before the hydration window)

Goal: the next hydration run succeeds and cannot take down the cluster.

### B.1 Isolate hydration workload from the control plane (aligned with dk-alchemy taxonomy) ✅ #303
- **Ephemeral-storage limits** on base Job `deploy/jobs/prestaged-hydrate.yaml`: `requests.ephemeral-storage: 5Gi`, `limits.ephemeral-storage: 20Gi`. An overrun evicts *the Job*, not the node.
- **`nodeAffinity` using the existing `dk.role` label**:
  ```yaml
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: dk.role
                operator: In
                values: [general]
  tolerations:
    - key: nvidia.com/gpu   # krang has this taint; tolerate it (GPU isn't used, but we must still land there)
      operator: Exists
      effect: NoSchedule
  ```
  Today that resolves to `krang` (k3s-slave-1) only — exactly where the `-17-slave` repair Job runs. This uses the existing taxonomy from dk-alchemy §2, so no new cluster-wide taint is needed.
- **`priorityClassName: production-critical`** (value 1,000,000, already defined in `k8s/infrastructure/priority-classes/`) for prod hydration. Staging hydration uses `staging-default`.
- **Toleration scrub**: no tolerations for `node.kubernetes.io/disk-pressure` — jobs must be evicted, not ride through.
- **Restore real CPU requests** (`500m`–`1`). The `10m` request in `deploy/jobs/prestaged-hydrate-incluster-17-slave.yaml:92-94` is a scheduling hack (obs 2527–2534) that thrashes QoS.

### B.2 Job-level resilience ✅ #303
- `activeDeadlineSeconds: 14400` on base (SC-002 is <4h)
- `backoffLimit: 3` with exponential delay (relies on existing `run_label` idempotency at `prestaged.py:353-455`)
- `restartPolicy: OnFailure` on hydrate container (loader is idempotent)
- **initContainer db-connectivity precheck** copied from `k8s/apps/infrastructure/base/db-migrate-job.yaml:30-42` — 5-attempt `psycopg2.connect` loop before the loader ever opens a dump file.

### B.3 Wire the manifest as a hard row-count gate ✅ #305
- In `prestaged.py` around line 426, require `expected_row_count` per `(schema, table)` from `prestaged_manifest.schema.json`; on mismatch beyond tolerance, status `row_mismatch` and non-zero per-step code.
- Missing manifest entries preserve current behavior but increment `dk_hydration_manifest_missing_total{source,schema,table}` so gaps are visible, not silent.

### B.4 Fix the zip extractor ✅ #307
- Replace "largest CSV" logic at `cms_downloader.py:520-536` with `extractall` into a per-source subdirectory.
- Emit one cached artifact per extracted file; each becomes its own manifest entry.
- Audit every fetcher that handles zips (30 grep matches: `cms_hcris.py`, `npi_registry.py`, `fda_ndc.py`, `cms_dual_eligible.py`, `cms_formulary.py`, `bindingdb.py`, `drugbank.py`, and others).
- Add `Content-Length` guard to `download_cms_file`: compare `written` against header; on mismatch, delete the `.tmp` and retry once.

### B.5 Missing alerts (PrometheusRules) ✅ #304
Add to `k8s/apps/observability/alert-rules/`:
- `DkNodeDiskPressure` — `kube_node_status_condition{condition="DiskPressure",status="true"} == 1` → critical
- `DkNodeEphemeralStorageHigh` — `node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.15` → warn
- `DkHydrationJobFailed` — `kube_job_status_failed{job_name=~".*hydrate.*"} > 0` → critical
- `DkCnpgNoPrimary` — primary-absent condition from the CNPG exporter for 2m → critical
- `DkHydrationRowMismatch` — `increase(dk_hydration_row_mismatch_total[1h]) > 0` → critical
- `DkPgBouncerPoolSaturation` — `pgbouncer_pools_server_active_connections / pgbouncer_pools_server_connections > 0.9` → warn

### B.6 CNPG disaster-recovery runbook (replaces any ArgoCD carve-out) ✅ #300
No changes to `selfHeal/prune` on `infra-cnpg-operator`. Instead, create `docs/runbooks/cnpg-operator-deadlock.md`:
1. **Detection**: `kubectl -n cnpg-system get pods` shows 0 Ready; Cluster CR stuck in `Creating`/`Recovering`; all writes fail.
2. **Triage**: confirm node conditions; if `DiskPressure: True`, ArgoCD will keep putting the operator back onto the tainted node.
3. **Emergency unblock path (no ArgoCD edits)**:
   - Free disk on the tainted node (`/var/lib/containerd/tmpmounts`, evicted pod volumes, dump files already mirrored to SeaweedFS).
   - `kubectl cordon` the tainted node → ArgoCD reconciles operator onto a healthy node → `kubectl uncordon` once recovered.
   - Last resort: `SELECT pg_promote()` on a replica, manual RW-service repoint.
4. **Postmortem**: capture in `.dk/memory/lessons.md` via the `lessons-learned` skill.
5. **Prevention**: B.1 makes this runbook an edge-case tool.

### B.7 Capture the incident in lessons ✅ #301
Two entries in `.dk/memory/lessons.md` (file is currently empty template):
- "Hydration on control-plane hostPath evicts Postgres operator" (obs 2482/2541)
- "ArgoCD selfHeal reconciles onto bad node — free the node, don't fight the reconciler" (obs 2608–2610)

### B.9 GitHub issue label taxonomy (create now) ✅ #299
One-time creation via `gh label create --repo data-kinetic/dk-data-FE` (and `data-kinetic/dk-cli` where relevant):
- `source:stub` / `source:fetcher_ready` / `source:live` — lifecycle state of a source entry
- `domain:mol` / `domain:hcs` / `domain:hcp` / `domain:ind` / `domain:ip` / `domain:dev` — new `dev` domain for medical devices (E.3)
- `tier:T1` / `tier:T2` / `tier:T3` / `tier:T4` — accessibility tier
- `priority:top15` — the 15 first onboardings (E.2)
- `procurement:pending` / `procurement:approved` / `procurement:blocked` — used for every T4 source (AHA, HCUP, IQVIA, Scopus, Dimensions, HIMSS, UMLS-SNOMED, STS, TQIP) so licensing tracking lives in issues, not in a spreadsheet
- `area:hydrate` / `area:data` / `area:observability` — routing
- `scope:immediate` / `scope:near-term` / `scope:scale-ready` — match this plan's horizons so issues auto-segregate

Label creation is idempotent (`gh label create` rejects duplicates — swallow that error).

### B.10 Confirm node labels are applied (dk-alchemy responsibility, we verify) ✅ labels live on cluster — dk-alchemy #651 closed
dk-alchemy §2 defines the labels `dk.role`, `dk.storage`, `topology.kubernetes.io/zone`. Per Phase 3 of the overview, retroactive labeling of penguin + krang happens during the Scarecrow join today (2026-04-16). Our job is to **verify** the labels are present before PR-01 opens so the affinity rule in B.1 actually binds:

```
kubectl get nodes -L dk.role,dk.storage,topology.kubernetes.io/zone
# Expected:
# penguin        dk.role=control  dk.storage=nvme-hdd  zone=penguin
# krang          dk.role=general  dk.storage=nvme-hdd  zone=krang
# scarecrow      dk.role=bulk     dk.storage=hdd       zone=scarecrow
```

If labels are missing, open a coordination comment on the dk-alchemy Phase 3 work (GH issue linked from the overview §12) asking for the retroactive `kubectl label node` to land first. **We do not run `kubectl label` directly** — that would trip the drift-protection stack (I.4).

This replaces the earlier "add a new taint" idea entirely. No taint is needed; the existing taxonomy is sufficient.

### B.11 Procurement tracking via GitHub issues ✅ #302 + dk-data-FE #290–#298
For every T4 licensed source (AHA Annual Survey, HCUP NIS/NEDS, IQVIA MIDAS, Scopus, Dimensions, HIMSS Analytics, UMLS/SNOMED-CT, ACS TQIP, STS National DB), open an issue via `gh issue create --repo data-kinetic/dk-data-FE` with labels `source:stub`, `tier:T4`, `procurement:pending`, and a body template:
- Data use case driving the ask
- Vendor / licensor + expected cost tier
- Decision-maker on the DataKinetic side
- Alternative T1/T2 sources that partially cover the need (so we don't block the roadmap on a single license)
- State transitions: `procurement:pending` → `procurement:approved` → issue unblocks the engineering ticket

This is the procurement "workflow" — no separate tracker needed.

### B.12 Verification (pre-window)
- Corrupt one dump; run loader; confirm `row_mismatch` status, no promotion.
- Fill staging-node ephemeral disk; confirm Job eviction without CNPG impact.
- Re-ingest NPPES; confirm all files extracted, row counts match manifest.
- Dry-run the runbook on staging CNPG; confirm unblock works without ArgoCD edits.

---

## Part C — Horizon 2: Near-term (1–4 weeks)

Goal: stabilize real-world failure modes, land SeaweedFS alignment, restore WAL backpressure, split the PgBouncer pool.

### C.1 SeaweedFS alignment (stay aligned to siblings; respect consumer-coupling-check) ✅ #311
- Endpoint **never hardcoded** in our manifests or code. The `consumer-coupling-check.yaml` CI gate blocks any diff adding literal `.infra.svc.cluster.local` URLs. Inject via a `DopplerSecret` that resolves to env vars `SEAWEEDFS_S3_ENDPOINT`, `SEAWEEDFS_S3_ACCESS_KEY`, `SEAWEEDFS_S3_SECRET_KEY`.
  - Target endpoint at runtime: `http://seaweedfs-s3.infra.svc.cluster.local:8333` (plain HTTP, S3 API on 8333 — not filer 8888, not master 9333).
  - SeaweedFS bulk data is mid-migration to the new 8 TB disk (dk-alchemy Phase 2.5 in-flight); cut dk-data-FE over **after** the rsync completes.
- Python client: boto3 with `signature_version="s3v4"`, **path-style addressing**, `region_name="us-east-1"`. **Copy** the pattern from `dk-alchemy:src/platform-api/src/platform_api/clients/minio_admin.py` — no importable package exists; deliberate copy per dk-alchemy's naming convention.
- New module `src/dk_data/ingestion/storage/minio_admin.py` (matching dk-alchemy's name — "MinIO" refers to the S3 *surface*, not the implementation). Exports: `put_artifact`, `get_artifact`, `list_prefix`, `presigned_url`. Idempotent bucket-create.
- Scratch PVC for restore: `local-path-bulk` storage class (dump artifacts are bulky, not latency-sensitive — do **not** land on `local-path-fast`). Size ~50Gi initially; tune as sources grow.
- Replace `hostPath` PVs in `deploy/jobs/prestaged-hydrate*.yaml` with an initContainer that pulls `s3://dk-data-prestaged/<run-label>/<schema>/<table>.dump` into the scratch PVC.
- Mirror CNPG `barmanObjectStore` to SeaweedFS for WAL archive + base backup — this is dk-alchemy side (issue #3 in I.5), not dk-data-FE. Track dependency.

### C.2 Real WAL backpressure (un-stub FR-007) ✅ #315 (migration 231)
- Create view `meta.wal_pressure` returning live pct-used against `max_wal_size` via `pg_current_wal_lsn()` + `pg_last_wal_receive_lsn()` on replicas.
- Replace the `0.0` stub at `src/dk_data/ingestion/wal_throttle.py:49-68`; preserve the 70/40 hysteresis (FR-007).
- Per-source pause budget in addition to the global one so one bad source can't drain the whole run.

### C.3 Dead-letter queue / source quarantine ✅ #316 (migration 232)
- Table `meta.hydration_backlog` (source_id, schema, table, last_failure_at, failure_count, last_error, next_retry_at, quarantined_by).
- Auto-quarantine after N (default 5) consecutive same-signature failures; manual re-enqueue only.

### C.4 Download integrity pipeline ✅ #313 (migration 229)
- `meta.artifact_provenance` records `Content-Length`, `ETag`, `Last-Modified`, `sha256` per artifact.
- Emit `dk_artifact_changed_total{source}` on upstream diff (signal for downstream rebuilds) and `dk_artifact_size_mismatch_total` on download/header mismatch.

### C.5 PgBouncer pool split ✅ #310 (+ dk-alchemy #656 follow-up)
- New pool `dk_data_hydration` with its own `max_client_conn` (default 20), separate from the PostgREST-facing `dk_data` pool.
- Update `k8s/apps/infrastructure/base/pgbouncer.yaml:41-50` to express the budget as math, not aspiration.

### C.6 Observability expansion ✅ #312
- `dk_hydration_phase_seconds{phase}` histogram (download/validate/restore/rowcount).
- `dk_artifact_bytes_total{source,kind}` counter.
- `dk_source_last_success_timestamp{source}` gauge.
- SLO: per-source hydration within declared `sla_seconds` at p95; alert on three consecutive breaches.

### C.7 SQLMesh audits at layer boundaries ✅ #314
- Silver: `not_null` on ER keys, `unique` on natural keys, `referential_integrity` on hub crosswalks.
- Gold: `row_count_within_pct` vs prior run, `freshness_seconds` budget.
- Most silver models have none today.

---

## Part D — Horizon 3: Scale-ready (4–12 weeks)

Goal: 73 → 200+ sources without new controllers and without growing ops headcount.

### D.1 Orchestrator decision — plain K8s Jobs per source, no workflow engine ✅ #322

**Decision: one `Job` (or `CronJob`) per source + a thin dispatcher Job, ordered from a source-registry table, rendered by kustomize, synced by the existing ArgoCD Application.**

Rationale (researched):
- **Sibling-repo precedent**: dk-alchemy runs *zero* workflow engines. Batch work there is plain `CronJob`. Adopting Argo Workflows / Temporal / Prefect / Dagster / Airflow would be the only new controller-class dependency across the platform.
- **In-repo precedent**: ~130 per-source `CronJob`s already live under `k8s/apps/cronjobs/base/`. The monolithic hydrate Job is the outlier, not the baseline.
- **Idempotency + DLQ exist already**: `meta.transform_runs.details->>'run_label'` (migration 229) plus the new `meta.hydration_backlog` from C.3.
- **Observability is already there**: Loki/Mimir/Alloy scrape Pod logs and `kube-state-metrics` emits Job/CronJob state — no new UI to deploy.
- **ArgoCD fit**: plain Jobs are immutable per run, `ttlSecondsAfterFinished` reaps them, selfHeal doesn't fight them.
- **Principle fit**: "simple, complete, senior." Argo Workflows adds a controller, CRDs, UI, and artifact-repo wiring for value that `meta.transform_runs` + Mimir alerts already cover.

Tradeoff accepted: a custom dispatcher must enforce tier ordering. Argo Workflows would give a DAG natively, but the tier graph is 8 tiers with declared `depends_on` — a ~200-line Python dispatcher is sufficient. Revisit only if (a) durable state beyond `meta.transform_runs` is needed, (b) fan-out exceeds ~500 parallel shells, or (c) a sibling repo adopts Argo Workflows first.

**Migration from today's monolithic Job**:
1. Parameterize `python -m dk_data.ingestion.prestaged --source <name> --run-label <label>` as the unit of work (the code already knows how to run a single source).
2. Source registry: `deploy/hydrate/sources.yaml` listing every source + tier + `depends_on`. Render per-source Job manifests into `k8s/apps/hydrate/base/job-hydrate-<source>.yaml` via a small `scripts/render_hydrate_jobs.py` (or kustomize `configMapGenerator`).
3. **Dispatcher Job** (`job-hydrate-dispatch.yaml`) reads `sources.yaml`, respects `meta.wal_pressure`, applies per-source Jobs in tier batches with bounded parallelism (`--max-parallel 4`). Uses the in-cluster kube API via its ServiceAccount; RBAC limited to `batch/jobs: create,get,list,watch`.
4. Wire under `k8s/apps/hydrate/` and reference from `k8s/overlays/prod/kustomization.yaml`; the existing ArgoCD Application picks it up.
5. Run new dispatcher parallel with the monolith for one cycle, compare `meta.transform_runs` rows for parity, then retire monolith manifests.

### D.2 Sources as declarative config ✅ #318 (migration 233)
Descriptor schema (replaces bespoke fetcher modules over time):

```yaml
# .dk/sources/chembl.yaml
name: chembl_molecules
domain: mol
tier: 2
depends_on: []
fetch:
  kind: postgres_dump       # or http_csv | http_json_paginated | zip | api_key
  artifact_uri: s3://dk-data-prestaged/chembl/molecules.dump
schedule: "0 3 * * 0"
credentials_ref: none
expected_row_count_fn: "SELECT reltuples::bigint FROM pg_class WHERE ..."
sla_seconds: 1800
manifest: .dk/sources/chembl.manifest.json
```

Descriptors drive: fetcher selection, manifest construction, Job rendering, dashboard rows, alert budgets. Behavior becomes data.

### D.3 Admission control by budget ✅ #320 (migration 234)
- `meta.resource_budget`: WAL headroom, PgBouncer slots, concurrent restores, SeaweedFS IOPS.
- Descriptor declares `consumes:` (e.g., `wal_headroom: 5%`, `db_connections: 2`).
- Dispatcher admits a source step only if budget has room; otherwise defers.

### D.4 Hard control-plane / data-plane isolation ⚠️ dk-data-FE side ✅ #317; cluster taint not yet applied — dk-alchemy #660 REOPENED
- Taint `node.datakinetic.com/role=control-plane:NoSchedule` on CNPG/ArgoCD/PgBouncer/observability nodes.
- No data-plane workload schedulable there — removes the class of failure that hit today.

### D.5 Per-source credential isolation ✅ #321 + dk-alchemy #661 + sweep #319
- Replace single `dk-data-secrets` DopplerSecret with per-source DopplerSecret CRs (`dk-data-secrets-drugbank`, `-openfda`, …).
- Rotation per source; compromise blast-radius is one source.

---

## Part E — Future data source roadmap

Coverage gaps are severe in three strategic areas: **medical devices (zero today)**, **global pricing/spend (zero outside US CMS)**, and **deep HCP data (NPI + ORCID only)**. Prioritization rule per user direction: **free or accessible/scrapable first**. Each stub becomes a descriptor (D.2), a README, and a GitHub issue for tracking.

### E.1 Tiering legend
- **T1** — Free, bulk download or open API, no registration
- **T2** — Free with registration / free API key
- **T3** — Accessible via scraping (public web, no paywall)
- **T4** — Licensed / commercial / paywalled

### E.2 Top 15 priority onboardings (all T1/T2, English, low volume, low effort)

1. `cms_hac_reduction` — single CSV, stable URL — **T1**
2. `cms_hrrp` — same pattern — **T1**
3. `cms_vbp` — same pattern — **T1**
4. `cms_open_payments` — annual CSV — **T1**
5. `pecos` — provider enrollment CSV — **T1**
6. `nih_reporter` — ExPORTER CSV — **T1**
7. `fda_enforcement` — openFDA JSON — **T2**
8. `fda_shortages` — openFDA — **T2**
9. `ema_epar` — EMA bulk CSV — **T1**
10. `health_canada_dpd` — zipped TXT — **T1**
11. `who_ghed` — WHO Global Health Expenditure Excel/CSV — **T1**
12. `worldbank_health` — World Bank REST API — **T1**
13. `oecd_health` — OECD SDMX/CSV — **T1**
14. `pbs_australia` — PBS XML schedule — **T1**
15. `research_orgs_ror` — Zenodo JSON dump (HCP hub seed) — **T1**

Each of these is a cache-a-file-and-parse job with no auth friction, no translation layer, and fits the existing `prestaged` / live-fetcher pattern with no infra changes.

### E.3 Full stub inventory (organized by domain × tier)

**Pharmaceutical (fill)**
- T1: `ema_epar`, `health_canada_dpd`, `ct_gov_eu_register`, `chebi`, `hmdb` (~5 GB), `open_targets` (>10 GB), `mesh`, `icd10`
- T2: `fda_enforcement`, `fda_shortages`, `who_ictrp`, `opentargets_platform_api`, `snomed_ct` (UMLS license), `rxnorm_history` (UMLS license)
- T3: `pmda_japan` (JA), `mhlw_japan` (JA) — queue behind a scrape/translation harness

**Medical devices (zero today → full build; new `dev_*` schemas)**
- T2: `fda_510k`, `fda_pma`, `fda_maude` (>10 GB), `fda_gudid` (>4 GB), `fda_device_recalls`, `fda_device_classification` — all openFDA, same pattern as drug endpoints
- T3: `eudamed`, `mhra_devices`, `nmpa_china_devices` (ZH), `pmda_japan_devices` (JA)
- Resolve function: `dev_silver.resolve_device()` keyed on UDI

**Hospital benchmarking (add depth)**
- T1: `cms_hac_reduction`, `cms_hrrp`, `cms_vbp`
- T3: `leapfrog_hospital_safety`
- T4 (deferred, procurement track): `hcup_nis` (>10 GB), `hcup_neds`, `aha_annual_survey`, `acs_tqip`, `sts_national_database`, `himss_analytics`

**Global spend / pricing (critical gap)**
- T1: `who_ghed`, `oecd_health`, `worldbank_health`, `nhs_openprescribing`, `nhs_secondary_care`, `pmprb_canada`, `pbs_australia`, `nice_tech_appraisals`
- T3 (scrape + translation): `hira_korea` (KO), `tlv_sweden` (SV), `aifa_italy` (IT), `cenetec_mexico` (ES), `cmed_brazil` (PT), `nppa_india`, `nhsa_china_vbp` (ZH), `cadth_canada`, `tlv_sweden_hta`
- T4: `iqvia_midas_sample`, `ihme_gbd` (free with account = T2, full >10 GB)

**HCP / researcher (deepen)**
- T1: `openalex` (>10 GB), `crossref` (>10 GB), `pubmed_incremental`, `europepmc`, `research_orgs_ror`, `cms_open_payments`, `nih_reporter`, `pecos`
- T4: `scopus`, `dimensions_ai` (free academic tier may be T2)

**IP (add global)**
- T2: `wipo_patentscope` (>10 GB)
- T3: `jpo_japan_patents` (JA, >10 GB), `kipo_korea_patents` (KO, >10 GB), `cnipa_china_patents` (ZH, >10 GB)

Rough totals: ~80 stubbed future sources; 35+ are T1/T2 (free and directly implementable).

### E.4 Stub README + GitHub issue pattern (per user direction) ⚠️ labels created; per-stub READMEs pending roadmap execution

For every stub, land two artifacts together:

1. **`.dk/sources/<name>/README.md`** — a one-page stub describing:
   - Domain & tier (e.g., `mol`, tier 2 in the load-order sense)
   - Access tier (T1–T4) + specific auth path (e.g., "free openFDA API key recommended but not required")
   - URL(s), schedule, expected volume, language, known gotchas
   - Schema sketch (what columns land in `<domain>_raw` / `_bronze`)
   - Status: `stub` | `specified` | `fetcher_ready` | `live`
   - Link to the tracking GitHub issue

2. **GitHub issue** opened at creation via `gh issue create --repo data-kinetic/dk-data-FE` — labels: `source:stub`, `domain:<domain>`, `tier:T1|T2|T3|T4`, plus `priority:top15` for the initial 15. Title: `feat(source): onboard <name> (<tier>)`. Body auto-generated from the README. Closes on merge of the fetcher.

Both artifacts are generated by the CLI scaffold (Part F). The `source:stub` label plus `.dk/sources/*/README.md` give a single index of future work that the team and Claude can both reason about.

---

## Part F — CLI strategy: target the new dk-cli (it's ready)

### F.1 Readiness — **yes, the new dk-cli is ready to extend** ✅ confirmed
Rechecked at the user's prompt. `/Users/nick/Code/dk-cli` is now a fresh-extracted monorepo (April 2026, v0.1.0) with git history preserved via `git filter-repo` from dk-alchemy:
- `src/dk-cli/` — TypeScript/Bun CLI (entry `src/index.ts`, bin `dk`). Existing commands under `src/commands/`: `data.ts` (data-API keys), `labels.ts`, `onboard.ts`, `provision.ts`, `status.ts`, `preview.ts`, `plugin.ts`, `adopt.ts`, `create.ts`, `promote.ts`, `llm.ts`, etc. Shared `src/lib/`: `github.ts`, `api-client.ts`, `auth.ts`, `telemetry.ts`, `template.ts`.
- `packages/dk-skills/` — Claude Code plugin (agents `cross-repo-triage`, `dk-audit`, `infra-health-check`, `milestone-checker`, `plan-alignment`, `preview-lifecycle`, `promotion-gate`; skills `dk-status`, `dk-create`, `dk-issues`, `dk-promote`, `dk-plan`, `dk-review`, `dk-health`, `dk-doppler`, `dk-labels`, `dk-llm`, …).
- `packages/dk-commands/` — command-manifest registry (`universal/speckit.*`, `dk-status`, `dk-test`, `dk-notify`, `dk-secrets`; `planning/dk-epic-execute`, `platform/speckit.implement`).
- `packages/dk-api-client/` — generated TS client for platform-api (OpenAPI).
- Workspace root: `CLAUDE.md` and `AGENTS.md` encode versioning + commit-message rules that CI enforces. `VERSION` + `CHANGELOG.md` + a tag of the form `dk-cli/vX.Y.Z` trigger multi-arch binary releases via `.github/workflows/dk-cli-release.yaml`.

The existing `src/dk-cli/src/commands/data.ts` is scoped to data-API-key lifecycle (create/list/rotate/update, usage, schemas, limits) against `platform-api`. The new hydration/source surface fits **beside** it as new `data` subgroups — no collision.

### F.2 Subcommand surface (added to `data.ts`, mirroring the existing `keys` / `usage` / `schemas` / `limits` branches) ✅ dk-cli PR #4 — Stage 1 scaffold, Stage 2 validate/lint/sync/list/bench, Stage 3 hydrate, Stage 4 skill+manifest

```
dk data source add <name>        # interactive scaffold (descriptor + fetcher + manifest + Job + README + GH issue)
dk data source validate <name>   # schema-check + dry-run fetcher + verify manifest
dk data source sync <name>       # one-off run against a staging DB
dk data source list [--tier N] [--status stub|fetcher_ready|live]
dk data source lint              # cross-source drift / stale-manifest check
dk data source bench <name>      # benchmark harness → meta.source_benchmarks
dk data hydrate run              # dispatch per-source Jobs via the in-cluster dispatcher
dk data hydrate status           # query meta.transform_runs for latest run
dk data hydrate backlog          # list meta.hydration_backlog + unquarantine
```

Each TS handler shells out via `execa` to `python -m dk_data.ingestion.<module>` (per-source work) or uses `@aws-sdk/client-s3` directly against SeaweedFS (C.1) for artifact operations, and the existing `lib/github.ts` for `gh issue create` on `data-kinetic/dk-data-FE`. No Python CLI surface needed.

### F.3 File layout (in `/Users/nick/Code/dk-cli`)
- `src/dk-cli/src/commands/data.ts` — **extend** with `source` and `hydrate` subcommand trees (new `dataSourceCommand` + `dataHydrateCommand`, registered on the existing `dataCommand` parent).
- `src/dk-cli/src/lib/source-scaffold.ts` — **new**: shared logic to render descriptor/manifest/README and call `lib/github.ts` for issue creation.
- `packages/dk-skills/skills/dk-data-source.md` — **new** Claude skill (replaces the deleted `.claude/commands/add-datasource.md` in dk-data-FE).
- `packages/dk-commands/universal/dk-data-source.md` — **new** command-manifest entry so the skill is distributable.
- Version bump + CHANGELOG entry per `CLAUDE.md` rules, tag `dk-cli/v0.2.0` for the feature release.

### F.4 dk-data-FE side (what the TS CLI calls into)
- `src/dk_data/ingestion/templates/*.j2` — Jinja templates for the four fetcher kinds (`http_csv`, `http_json_paginated`, `zip_bundle`, `postgres_dump`) — invoked by the TS scaffolder via `python -m dk_data.ingestion.templates.render`.
- `src/dk_data/ingestion/common/{retry,integrity,metrics}.py` — shared runtime deps for generated fetchers.
- `.dk/sources/<name>/{descriptor.yaml,manifest.json,README.md}` — generated per-source tree.

This keeps the ingestion runtime in Python (where it already lives) and the UX in TS (where the platform CLI already is).

### F.5 One-time coordination issue on `data-kinetic/dk-cli`
Open a single tracking issue titled `feat(data): add source + hydrate subcommands for dk-data-FE` linking to:
- This plan file
- The `src/dk-cli/src/commands/data.ts` extension points
- The dk-data-FE Python module names the TS handlers shell into

Labels: `area:data`, `scope:feature`. The remaining migration-housekeeping TODOs from dk-cli's README (hard-coded `REGISTRY_REPO = "dk-alchemy"` in `plugin.ts` / `commands.ts`, the install.sh one-liner, `bun run generate:api-client` alias) are separate dk-cli issues — flag if they block; otherwise do not adopt them.

### F.4 Scaffold templates produced by `source add`

Four Python fetcher templates under `src/dk_data/ingestion/templates/*.j2`:
- `http_csv.py.j2` — `requests.get(stream=True)` + `Content-Length` guard + SHA256 + single-file write
- `http_json_paginated.py.j2` — cursor/next_page loop, rate-limit handling, last-page integrity check
- `zip_bundle.py.j2` — `extractall` into per-source dir, per-file manifest
- `postgres_dump.py.j2` — `pg_dump` against a source-side replica → `s3://dk-data-prestaged/<source>/<table>.dump`

Each imports `src/dk_data/ingestion/common/{retry,integrity,metrics}.py` so new fetchers don't reinvent retry, digest, or metrics.

`dk data source add` writes all of:
- `.dk/sources/<name>/descriptor.yaml` (D.2 schema)
- `.dk/sources/<name>/manifest.json`
- `.dk/sources/<name>/README.md` (E.4)
- `src/dk_data/ingestion/fetchers/<name>.py` (from template)
- `src/dk_data/sqlmesh/models/<domain>/{raw,bronze,silver,gold}/<name>.sql` scaffolds
- `deploy/hydrate/sources.yaml` entry (appended)
- GitHub issue via `gh issue create`

### F.5 Claude skill: `/dk.add-datasource` ✅ `packages/dk-skills/skills/dk-data-source.md` landed via dk-cli PR #4 Stage 4
Restore (the old command was deleted in this working tree per `git status`). Skill flow:
1. AskUserQuestion for domain, tier, cadence, fetch kind, auth, expected-row-count signal, SLA.
2. Grep existing fetchers for similar kind; propose reusing templates before inventing.
3. Shell `python -m dk_data source add <name>` (today) / `dk data source add <name>` (after TS migration) to scaffold.
4. Offer `source validate` and `bench` in a dev namespace.
5. Draft a `/dk.specify` brief for formal feature-review so every new source carries the same spec discipline as a feature.

### F.6 Governance / CI gate
- Every source PR: descriptor + manifest + README + fetcher + one bronze model + one silver audit.
- CI gate: `source lint` passes, `source validate` against staging SeaweedFS passes.
- Merged sources auto-appear on the hydration dashboard (dashboard reads `meta.source_registry`).

---

## Part J — Dashboards & telemetry: in-repo, repo-owned, ArgoCD-deployed

**Principle per user direction**: "stop teams from reaching into alchemy for their projects." Each project owns its own dashboards. dk-data-FE's observability surface lives in dk-data-FE, not in dk-alchemy.

### J.1 Current situation ✅ (captured; dk-data-FE owns its dashboards as of #306)
- 6 dk-data JSON dashboards already exist at `grafana/dashboards/` in dk-data-FE (`dk-data-platform-status`, `dk-data-pipeline-sources`, `dk-data-transformations`, `dk-data-api-services`, `dk-data-adapter-telemetry`, `cms-pipeline-health`).
- 7+ additional dk-data dashboards live **in dk-alchemy** at `grafana/dashboards/applications/dk-data-*.json` — the exact anti-pattern.
- dk-alchemy runs plain `grafana/grafana:11.3.0` (`k8s/infrastructure/grafana/base/deployment.yaml`): **no grafana-operator, no sidecar dashboard loader, no provisioning mount.** Dashboards are pushed via HTTP API by a GitHub Action (`.github/workflows/grafana-dashboards.yaml`) that shells `grafana/scripts/sync-all.sh` → `import-dashboard.sh` → `curl` against `https://grafana.behaviorlabs.ai/api/dashboards/db`, using `GRAFANA_API_KEY` from Doppler `dk-infrastructure/prd`.
- Grafana service: `grafana.infra.svc.cluster.local:3000`. Datasource UIDs (hard-coded in `configmap.yaml`): mimir `PAE45454D0EDB9216`, loki `P8E80F9AEF21F6940`, tempo `P214B5B846CF3925F`. Folders declared in `grafana/folders/folders.yaml` — `applications` already exists.

### J.2 Recommendation — two-step ⏸️ Step 1 ✅ #306; Step 2 grafana-operator deferred — dk-alchemy #647
**Step 1 (Horizon 2, zero touches to dk-alchemy): mirror the push-via-API pattern in dk-data-FE.**

- Create in dk-data-FE:
  - `grafana/dashboards/` (already exists — 6 JSON files)
  - `grafana/folders/folders.yaml` declaring folder `dk-data-fe` (new, or append under existing `applications`)
  - `grafana/scripts/` with a vendored copy of `sync-all.sh` + `import-dashboard.sh` (or reference them as a git-submodule on dk-alchemy; vendor is simpler).
  - `.github/workflows/grafana-dashboards.yaml` — identical to dk-alchemy's, with `paths: ['grafana/**']` filter. Pull `GRAFANA_API_KEY` from the same Doppler project via a repo-level `DOPPLER_TOKEN`.
- **UID discipline**: prefix every dashboard UID with `dk-data-fe-` so the sync (last-write-wins by UID) can't collide with dk-alchemy-owned dashboards. Rename the existing 6 JSONs to match.
- Coordinate with the dk-alchemy owner: delete the 7 dk-data dashboards currently at `dk-alchemy/grafana/dashboards/applications/dk-data-*.json` in a single PR *after* the dk-data-FE workflow is green; they get re-imported automatically from the new home.

**Step 2 (Horizon 3, requires one dk-alchemy PR): install `grafana-operator` as the shared mechanism.**

- dk-alchemy PR installs `grafana-operator` in `infra`, adds a `Grafana` CR (`external=true`) labeled `dashboards=behaviorlabs`, and keeps backward compatibility for the push-API path.
- dk-data-FE then emits `GrafanaDashboard` CRs under `k8s/apps/observability/dashboards/`:

  ```yaml
  apiVersion: grafana.integreatly.org/v1beta1
  kind: GrafanaDashboard
  metadata:
    name: dk-data-fe-hydration
    namespace: dk-data-fe
  spec:
    instanceSelector: { matchLabels: { dashboards: "behaviorlabs" } }
    folder: applications
    json: |
      { ... }
  ```

- **ArgoCD Application** for dashboards, owned by this repo — `.gitops/prod/apps/dk-data-fe-observability.yaml`, path `k8s/apps/observability/` in dk-data-FE, syncs alert rules + dashboard CRs. The existing Application for dk-data-FE (`.gitops/prod/apps/application.yaml`) stays focused on the app; observability gets its own Application to isolate sync scopes and make dashboard changes auditable without touching the app.
- This step removes the Doppler-token cross-wiring from Step 1 and gives typed, namespaced, RBAC-scoped ownership.

### J.3 Dashboards specifically needed for the work in this plan ⚠️ stubs exist; C.2/C.3/D.3 panel content pending follow-up
Beyond the 6 existing, add:
- `dk-data-fe-hydration` — per-source run status from `meta.transform_runs`, current step, row_count vs expected, p50/p95 per-source duration, failures in last 24h.
- `dk-data-fe-hydration-backlog` — `meta.hydration_backlog` rows with failure signature, last_error, quarantine reason.
- `dk-data-fe-wal-pressure` — `meta.wal_pressure` timeline, pause events, budget consumption.
- `dk-data-fe-seaweedfs-artifacts` — `meta.artifact_provenance` freshness, download bytes/min, size-mismatch events.
- `dk-data-fe-resource-budget` — `meta.resource_budget` utilization (WAL headroom, PgBouncer slots, concurrent restores).
- `dk-data-fe-source-registry` — source count by tier/domain/status (stub/fetcher_ready/live), onboarding velocity.

Alert rules (Part B.5) co-locate under `k8s/apps/observability/alert-rules/` in dk-data-FE, deployed through the same ArgoCD Application — the dashboards show the alerts' underlying metrics in context.

### J.4 Telemetry emission — repo-owned too ✅ (pre-existing; no changes needed)
- Prometheus metrics from `src/dk_data/observability/metrics.py` already scrape via Alloy → Mimir (dk-alchemy-hosted). No changes needed on the emitter side; what was missing is the dashboard side, solved by J.1–J.3.
- OTLP traces: emitter already injects `trace_id`/`span_id` via `src/dk_data/observability/logging.py`. Targets dk-alchemy-hosted Tempo. No change.
- The principle "repo owns its dashboards" doesn't mean repo owns Grafana/Tempo/Mimir — those remain platform-managed in dk-alchemy. The split: **platform hosts the observability backends; each project authors and ships its own views.**

---

## Part G — Critical files touched

- `src/dk_data/ingestion/prestaged.py` — manifest row-count gate (B.3), `--source` single-source mode (D.1), structured error reporting
- `src/dk_data/ingestion/wal_throttle.py` — un-stub pressure (C.2)
- `src/dk_data/ingestion/downloaders/cms_downloader.py` — zip extractor + Content-Length guard (B.4)
- `src/dk_data/ingestion/fetchers/**` — audit for zip + streaming patterns (B.4)
- `src/dk_data/ingestion/storage/minio_admin.py` — **new** SeaweedFS client, naming matches dk-alchemy (C.1)
- `src/dk_data/ingestion/common/{retry,integrity,metrics}.py` — **new** shared template deps (F.3)
- `src/dk_data/ingestion/templates/*.j2` — **new** fetcher templates (F.3)
- `src/dk_data/ingestion/prestaged_manifest.schema.json` — required, not optional (B.3)
- `src/dk_data/observability/metrics.py` — new counters (B.3, B.4, C.4, C.6)
- `deploy/jobs/prestaged-hydrate.yaml` — limits/probes/affinity (B.1, B.2); phased retirement after D.1
- `deploy/hydrate/sources.yaml` — **new** source registry that renders per-source Jobs (D.1, D.2)
- `k8s/apps/hydrate/base/` — **new** per-source Job manifests + dispatcher (D.1)
- `k8s/apps/infrastructure/base/pgbouncer.yaml` — split pool (C.5)
- `k8s/apps/observability/alert-rules/` — new PrometheusRules (B.5)
- `scripts/render_hydrate_jobs.py` — **new** renderer (D.1)
- `docs/runbooks/cnpg-operator-deadlock.md` — **new** (B.6)
- `.dk/memory/lessons.md` — today's two lessons (B.7)
- `.dk/sources/**/{descriptor.yaml,manifest.json,README.md}` — **new** per-source declarative tree (D.2, E.4)
- `.claude/commands/dk.add-datasource.md` — **restored** Claude skill (F.4)
- `/Users/nick/Code/dk-cli/src/commands/data/**` — **new** `dk data *` TS commands (F.2)
- `src/dk_data/sql/migrations/` — new migrations for `meta.hydration_backlog` (C.3), `meta.artifact_provenance` (C.4), `meta.resource_budget` (D.3), `meta.source_registry` + `meta.source_benchmarks` (D.2/F.1), `meta.wal_pressure` view (C.2)

---

## Part H — Verification

### H.1 Immediate (pre-window)
- Corrupt one dump → loader returns `row_mismatch`, no promotion.
- Fill a staging node's ephemeral disk → Job evicted, CNPG unaffected.
- Re-ingest NPPES → every CSV inside the zip restored, row counts match manifest.
- Dry-run runbook on staging CNPG → unblock path works with no ArgoCD edits.

### H.2 Near-term
- SeaweedFS cutover: fetch one source → `s3://dk-data-prestaged/` → initContainer restore; row counts match hostPath path.
- Induce WAL load in a parallel session → loader pauses above 70%, resumes below 40%.
- Simulate repeatable failure → after 5 tries, source is in `meta.hydration_backlog` and no longer scheduled.

### H.3 Scale-ready
- 20 synthetic per-source Jobs + dispatcher → one poisoned source does not block the other 19.
- Pin budget to 10 concurrent; queue 30 sources → dispatcher admits at most 10.
- `dk data source add synthetic_demo` → descriptor + manifest + README + fetcher + model scaffolds + GH issue all generated; `validate` passes; `bench` writes `meta.source_benchmarks` row; source appears on dashboard.
- Node taints from B.10 hold: try to schedule a tolerations-less hydrate Pod onto the control-plane node; confirm it stays Pending until the taint is removed.
- Label taxonomy from B.9 is present on `gh label list`.
- At least one T4 procurement issue exists with `procurement:pending`.

---

## Part I — Execution & coordination

### I.1 Coordination
This is the sole agent working in the project — no cross-agent guard rails needed. PRs merge as soon as CI passes.

### I.2 PR-per-subsection execution order (Horizon 1) ✅ all 11 H1 PRs landed

Horizon 1 lands as **10 atomic PRs**. PR-01 bundles B.1 + B.2 + B.10 because all three edit `deploy/jobs/prestaged-hydrate*.yaml` — splitting would serialize unnecessarily. Every other PR touches a disjoint file set and can ship in any order.

| # | Title | Scope | Repo | Files |
|---|-------|-------|------|-------|
| **PR-01** | `feat(hydrate): isolate + resilient Job manifests` | B.1 + B.2 + B.10 | dk-data-FE | `deploy/jobs/prestaged-hydrate*.yaml`, node-label verification script |
| **PR-02** | `feat(hydrate): manifest row-count gate` | B.3 | dk-data-FE | `src/dk_data/ingestion/prestaged.py`, `prestaged_manifest.schema.json` |
| **PR-03** | `fix(ingest): extract all files from zip + Content-Length guard` | B.4 | dk-data-FE | `src/dk_data/ingestion/downloaders/cms_downloader.py` + zip-using fetchers |
| **PR-04** | `feat(observability): missing alert rules` | B.5 | dk-data-FE | `k8s/apps/observability/alert-rules/*.yaml` |
| **PR-05** | `docs(runbook): CNPG operator deadlock` | B.6 | dk-data-FE | `docs/runbooks/cnpg-operator-deadlock.md` |
| **PR-06** | `docs(lessons): hydration + ArgoCD selfHeal incidents` | B.7 | dk-data-FE | `.dk/memory/lessons.md` |
| **PR-07** | `chore(gh): create label taxonomy` | B.9 | dk-data-FE, dk-cli | `scripts/bootstrap-gh-labels.sh` (idempotent `gh label create`) |
| **PR-08** | `feat(ingest): procurement tracking via GH issues` | B.11 | dk-data-FE | `scripts/open-procurement-issues.sh`, runs once to open ~9 issues |
| **PR-09** | `feat(observability): own dashboards in-repo (push-via-API)` | Part J step 1 | dk-data-FE | `grafana/`, `.github/workflows/grafana-dashboards.yaml` |
| **PR-10** | `chore(dk-alchemy): delete orphan dk-data dashboards` | I.3 #1 | dk-alchemy | `grafana/dashboards/applications/dk-data-*.json` — deletion-only, gated on PR-09 being green |

**Parallelization**: PR-01 through PR-09 are fully file-independent → launchable concurrently as nine parallel worktree-isolated agents per `superpowers:subagent-driven-development`. PR-10 is sequential (gates on PR-09 + different repo).

Horizon 2 and 3 PRs (SeaweedFS alignment, WAL backpressure, DLQ, integrity pipeline, pool split, SQLMesh audits, dispatcher + per-source Jobs, descriptors, admission control, per-source credentials, grafana-operator migration) follow the same per-subsection discipline and break into parallel waves by file-independence.

### I.3 Remaining cross-repo items ⏸️ tracked via dk-alchemy issues #646 (closed), #647–#651, #656, #659–#661
1. **Delete the orphan dk-data dashboards from dk-alchemy** — PR-11 above, gated on PR-10. One dk-alchemy PR scoped to deletion.
2. **Move to `grafana-operator` (Part J step 2)** — single dk-alchemy PR to install the operator + label the Grafana with `dashboards=behaviorlabs`. Unblocks CR-based dashboard ownership; defer until ≥2 sibling repos have migrated dashboards out of dk-alchemy.
3. **CNPG `barmanObjectStore` cutover to SeaweedFS** — needs a short maintenance window + verified base backup before flipping the archive target.
4. **dk-cli version bump & release** — once `data.ts` extension merges, tag `dk-cli/v0.2.0` per the dk-cli CLAUDE.md rules so dk-data-FE CI can depend on a specific CLI version rather than floating `main`.

### I.4 Pre-flight answers (from `dk-alchemy/dk-alchemy-2-overview.md`)

Reading the canonical overview resolved every pre-flight question and added several guardrails. Summary of the ground truth that reshapes PR-01 and downstream work:

**Cluster topology**
- `penguin` (k3s-master-1, 10.0.0.11) — control-plane + general + NVMe + HDD, zone `penguin`
- `krang` (k3s-slave-1, 10.0.0.12) — general + NVMe + GPU (nvidia), taint `nvidia.com/gpu=true:NoSchedule`, zone `krang`
- `scarecrow` — **joining today 2026-04-16** as `k3s-slave-2` (worker), later promoted to `k3s-master-2` after sqlite→etcd migration (Phase 3.5). Bulk-storage-only, 10 TB bulk disk from `bulk-images` ZFS pool, zone `scarecrow`
- Edge LBs `phantom` (10.0.0.2) + `venom` (10.0.0.3) — separate from K3s

**Existing node taxonomy (use this, do not invent a new one)**
- Label `dk.role` with values `control | general | bulk`
- Label `dk.storage` with values `nvme-hdd | hdd`
- Label `topology.kubernetes.io/zone` with values `penguin | krang | scarecrow`
- **No blanket control-plane taint today** — the only existing taint is krang's GPU taint
- **Therefore** our hydration Job should use `nodeAffinity: dk.role In (general)` and `nodeSelector: topology.kubernetes.io/zone In (krang, scarecrow)` — **not** a new `role=control-plane:NoSchedule` taint. This aligns with the existing placement-contract vocabulary in §2 of the overview.
- Today that resolves to `krang` only; after scarecrow's master promotion it remains `krang` only (scarecrow stays `dk.role=bulk`); after a third general node joins it spreads naturally.

**Storage classes**
- `local-path-fast` — NVMe, for OLTP (postgres, redis)
- `local-path-bulk` — ZFS-backed HDD, for observability + SeaweedFS
- `local-path-db-large` — new, ZFS bulk on penguin, earmarked for **dk-data postgres isolation** (dk-alchemy Phase 8)
- `local-path` (legacy) — being phased out
- All use `WaitForFirstConsumer` + `allowVolumeExpansion: true`
- **Our hydrate scratch PVC** — use `local-path-bulk` (dump artifacts are bulky, not latency-sensitive). Do **not** land on `local-path-fast`.

**Priority classes**
- `production-critical` = 1,000,000 and `staging-default` = 100,000 already exist
- Hydration Jobs in prod namespace get `production-critical`; staging hydration gets `staging-default`

**Active drift-protection stack (live as of 2026-04-15, Audit/warn mode)**
- Layer 1: Claude Code `PreToolUse` hook at `dk-alchemy:infra/drift-protection/dk-cluster-guard.sh`
- Layer 2: `dk-kubectl` wrapper at `dk-alchemy:infra/drift-protection/dk-kubectl.sh`
- Layer 3: Kyverno `warn-non-argocd-writes` ClusterPolicy
- Protected namespaces include `infra`, `infra-staging`, `cnpg-system`, `kyverno`, `*-prod` (so `dk-data-prod` too)
- **Implication**: every change in this plan must land via ArgoCD sync, never direct `kubectl apply`. Our PRs are the only path.

**Consumer coupling check (enforced in CI)**
- The reusable workflow `consumer-coupling-check.yaml` fails our CI if a diff introduces: hardcoded `.infra.svc.cluster.local` URLs, new files under `dk-alchemy/k8s/`, or new PreSync hooks mutating shared platform storage.
- **Implication**: the SeaweedFS endpoint (C.1) must be injected via `DopplerSecret`, not hardcoded; our repo cannot add manifests to `dk-alchemy/k8s/**` — alchemy-side work must be separate PRs on dk-alchemy.

**ArgoCD bootstrap already in place**
- `dk-alchemy:.gitops/external/dk-data-fe.yaml` registers `dk-data-bootstrap-prod` + `dk-data-bootstrap-staging`. Our new observability Application (Part J) lands inside this bootstrap tree — no new bootstrap needed.

**Staging branch adoption is pending** (dk-alchemy Phase 5.5)
- dk-data-FE does **not yet have a `staging` branch**. Horizon 1 PRs target `feature/005-prestaged-hydration` or `main` (current working branch is `feature/005-prestaged-hydration`). Opening a `staging` branch is itself a Horizon 2 item, coordinated with dk-alchemy Phase 5.5.

**Platform state is past Phase 0**
- Phase 0 emergency (postgres writes restored, 961 GB orphan deleted, postgres-cluster-14 promoted) is DONE as of 2026-04-15.
- Phase 2.5 (8 TB bulk disk hot-added) is DONE; SeaweedFS rsync to new disk is IN-FLIGHT.
- **Therefore**: today's failure from session memory (obs 2482, 2541, 2608) has already been recovered operationally on the alchemy side. Our Horizon 1 is now about preventing recurrence, not mid-incident firefighting.

**Platform versioning**
- dk-alchemy is at platform version `2.0.0` (plain-text `VERSION` + `CHANGELOG.md`). Agents/humans PATCH-bump on phase completion; MINOR/MAJOR require user request. dk-cli follows its own `dk-cli/vX.Y.Z` tag convention (Part F).
- Our PRs don't bump dk-alchemy's `VERSION` — those bumps are owned by dk-alchemy work.

### I.5 GitHub issues to open on sibling repos (drafted, fired on ExitPlanMode)

**On `data-kinetic/dk-alchemy`** — gh issue create commands ready to run:

1. **Title**: `chore(grafana): delete orphan dk-data-*.json dashboards (dk-data-FE now owns its own)`
   - Labels: `area:grafana`, `scope:cleanup`, `consumer:dk-data-fe`
   - Body: references the 7 files at `grafana/dashboards/applications/dk-data-*.json`, gates on dk-data-FE PR-10 being green, asks for a deletion-only PR, lists the UID namespacing (`dk-data-fe-*`) to confirm no collision.

2. **Title**: `feat(grafana): install grafana-operator for CR-based dashboard ownership`
   - Labels: `area:grafana`, `scope:feature`, `phase:after-phase-5`
   - Body: rationale for `grafana-operator` per our plan Part J step 2 (typed, namespaced, RBAC-scoped ownership; removes Doppler-token cross-wiring). Recommends deferring until ≥2 sibling repos have migrated. Links to this plan.

3. **Title**: `feat(cnpg): barmanObjectStore → SeaweedFS S3 gateway for WAL archive + base backup`
   - Labels: `area:cnpg`, `scope:feature`, `phase:post-seaweedfs-migration`
   - Body: the SeaweedFS bulk migration referenced in alchemy Phase 2.5 is in-flight; once SeaweedFS is stable at new home, flip `barmanObjectStore.destinationPath` from `s3://postgres-backups/...` endpoint to `http://seaweedfs-s3.infra.svc.cluster.local:8333` with a verified base backup. Lists test: `barman-cloud-wal-archive --test`.

4. **Title**: `feat(platform): accelerate dk-data postgres migration to local-path-db-large`
   - Labels: `area:postgres`, `area:dk-data`, `scope:feature`, `phase:8` (matches the deferred Phase 8 item in §14)
   - Body: the "separate physical isolation for dk-data postgres" plan in §14 of the overview is the structural fix for today's co-tenant eviction failure. Our hydration robustness work pushes up demand — request this move up the roadmap.

5. **Title**: `chore(dk-data-fe): create staging branch + register service in staging-slos.yaml`
   - Labels: `area:ci`, `phase:5.5`, `consumer:dk-data-fe`
   - Body: per dk-alchemy §8, dk-data-fe needs `staging` branch + dual-branch build workflow + entry in `src/grafana-github-webhook/configs/staging-slos.yaml` (error_rate_threshold, latency_p95_threshold_ms, soak_hours). Proposes: error 0.5%, p95 1000ms, soak 4h (data pipeline, slower feedback tolerable). dk-data-FE side opens the branch and updates `.gitops/*/apps/` targetRevisions; dk-alchemy side registers the SLOs.

**On `data-kinetic/dk-cli`** — gh issue create commands ready to run:

1. **Title**: `feat(data): add source + hydrate subcommands for dk-data-FE (from Plan v5)`
   - Labels: `area:data`, `scope:feature`
   - Body: extension points under `src/dk-cli/src/commands/data.ts` alongside existing `keys/usage/schemas/limits`. Subcommand tree per Part F.2. References dk-data-FE Python modules the TS handlers shell into (`python -m dk_data.ingestion.*`). Lists file layout from Part F.3 including the new `lib/source-scaffold.ts`. Target release `dk-cli/v0.2.0`.

2. **Title**: `chore(registry): add dk-data-source skill + command manifest`
   - Labels: `area:skills`, `area:commands`, `scope:feature`
   - Body: add `packages/dk-skills/skills/dk-data-source.md` (restored Claude skill per Part F.5) and `packages/dk-commands/universal/dk-data-source.md` (manifest entry). Mirrors the deleted `.claude/commands/add-datasource.md` in dk-data-FE but lives in the shared registry for multi-repo reuse.

3. **Title**: `chore(meta): track Horizon 1–3 dk-data-FE work for CLI alignment`
   - Labels: `tracking`, `area:data`
   - Body: single tracking issue with checkboxes for each dk-data-FE Horizon 1/2/3 item that requires CLI support (scaffold, validate, bench, lint, hydrate run/status/backlog). Cross-links to dk-data-FE PRs as they land.

### I.6 Ready for remote-trigger execution — parallel workers

Once this plan is approved (ExitPlanMode), the first session runs five serial "setup" steps, then dispatches nine parallel worktree agents for PR-01 through PR-09, then one sequential agent for PR-10.

**Setup (serial, this session)**
1. **Write** a copy of this plan to `/Users/nick/Code/dk-data-FE/plan.md` (overwrites the existing untracked file).
2. **Open** all 8 cross-repo issues listed in I.5 via `gh issue create` (5 on `data-kinetic/dk-alchemy`, 3 on `data-kinetic/dk-cli`) using HEREDOC bodies. Capture the issue URLs into the plan for cross-referencing.
3. **Bootstrap** the GH label taxonomy per B.9 on both dk-data-FE and dk-cli via idempotent `gh label create`. (This is the part of PR-07's content that must predate PR-08.)
4. **Open** the 9 T4 procurement issues per B.11 on dk-data-FE with labels `source:stub`, `tier:T4`, `procurement:pending`.
5. **Verify** node labels (`kubectl get nodes -L dk.role,dk.storage,topology.kubernetes.io/zone`) per B.10 — if missing, pause PR-01 and comment on dk-alchemy Phase 3 issue; otherwise proceed.

**Execution (parallel, `superpowers:subagent-driven-development`)**
6. Dispatch **nine concurrent worker agents** via `Agent` tool calls in a single message, each:
   - Working in a dedicated worktree (`superpowers:using-git-worktrees`)
   - Branching from `feature/005-prestaged-hydration`
   - Scoped to exactly one PR from the I.2 table (PR-01…PR-09)
   - Required to ship passing CI + open the PR at the end of its turn
   - Returning a ≤200-word status report with the PR URL
7. Track completion by polling `gh pr list --author @me --state open --repo data-kinetic/dk-data-FE`. As PRs merge, worktrees auto-clean (per the worktree skill).

**Finalization (serial, after PR-09 merges)**
8. Dispatch **one worker** for PR-10 (dk-alchemy orphan dashboard deletion) once `gh pr view <PR-09> --json state` returns `MERGED`.
9. Commit and push the plan copy in `plan.md` as the ship-of-record.

**Idempotency**
- Every setup step uses idempotent primitives (`gh label create` returns an error for duplicates which we swallow, `gh issue create` is safe to retry by checking for an existing open issue with the same title, plan write is overwrite).
- A `RemoteTrigger` re-invocation can safely rerun steps 1–5 without duplicating issues (pre-check by title) or labels.

**Horizon 2 / 3 follow-up**
After Horizon 1 ships, the same pattern scales to Horizon 2 (SeaweedFS/WAL/DLQ/integrity/pool/audits) and Horizon 3 (dispatcher/descriptors/admission/per-source credentials/grafana-operator). Each subsection maps to a PR; `superpowers:subagent-driven-development` with file-independent workers applies identically.

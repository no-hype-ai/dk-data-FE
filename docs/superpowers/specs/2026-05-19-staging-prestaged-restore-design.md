# Staging prestaged restore — design

**Date:** 2026-05-19 · **Status:** approved (design) · Feature 211 / WS4 follow-on
· Unblocks SP3 (`specs/211-ws4-staging-main-reconcile/sp3-design.md`)

## Problem

SP3 suspends every `^fetch-.*` CronJob in the **staging** overlay so external
sources are fetched once (in prod) instead of twice (FR-011 / SC-005). But
staging and prod use **separate Postgres instances**
(`postgresql.infra-staging` vs `postgresql.infra`,
`docs/PLATFORM_GUIDE.md:485`). With staging's fetchers suspended and no
replacement data path, staging's `dk_data` raw layer goes stale. SP3's own
design (`sp3-design.md:41`) names this the operational precondition:
*"staging's prestaged-hydration pipeline must be provisioned … before/with
this change."* This document is that pipeline.

## Discovered topology (decisive)

- **Consumer** `src/dk_data/ingestion/prestaged.py` is a pure local-FS walk of
  `PRESTAGED_ROOT`; it never pulls from S3 and expects a per-`(schema,table)`
  `.dump` tree (`_staging/<archive>/dk-data-files/{schema}/{table}/*.dump` or
  `_loose_dumps/{schema}/*.dump`).
- **No automated per-source producer exists.** Feature-005's artifacts arrive
  "via Drive" (manual). The `ObjectStore` SeaweedFS client
  (`src/dk_data/ingestion/storage/minio_admin.py`) was landed but explicitly
  *not* wired into the hydration flow (`docs/runbooks/seaweedfs-client.md`).
- The `k8s/apps/hydrate/` per-source fan-out is hardcoded
  `namespace: dk-data-prod`, auto-generated, and referenced by **no** overlay
  — it cannot serve staging.
- **Prod already produces one "created-once" artifact daily.**
  `pg-backup-daily` (`k8s/apps/infrastructure/base/backup/pg-backup-daily.yaml`,
  schedule `0 12 * * *`) runs `pg_dump -Fc -Z6` of `dk_data` **excluding** the
  two structurally-oversized, SQLMesh-re-derivable bronze tables
  (`mol_bronze.*chembl_activities*`, `mol_bronze.*pubchem*`) and uploads to
  SeaweedFS `postgres-backups/dk-data-prod/daily/dk_data_<ts>_daily.dump`.
  `pg-backup-weekly` (`0 3 * * 0`) is the full ~434 GB dump.
- Staging's overlay **repoints `minio-backup-credentials` and the pg-backup
  `MINIO_ENDPOINT` to staging's own store** (`infra-staging`) — those creds
  read staging's store, not prod's.
- A proven `mc → pg_restore` recipe already exists in `verify.sh`
  (`pg-backup-configmap.yaml`): `mc alias set` → `mc ls … | tail -1` → `mc cp`
  → `pg_restore --list` object-count gate.

## Strategy (Approach A — reuse prod's existing daily dump)

Do **not** build a producer, a per-source tree, or an S3→PVC sync. Treat
staging as a **consumer of prod's existing `pg-backup-daily` artifact**. One
new staging-only CronJob downloads the latest prod daily dump and
`pg_restore`s it into staging's `dk_data`. SP3-kept SQLMesh transforms
re-derive the two excluded bronze tables from restored raw and re-promote.

**Source = daily** (user decision): ~200 GB, refreshed every 24 h, omits only
the two re-derivable bronze tables. (Weekly-full and daily-with-weekly-fallback
were considered and rejected — heavier / unnecessary for a disposable mirror.)

Data flow:

```
prod fetchers → prod dk_data → pg-backup-daily (0 12 * * *, EXISTING, created ONCE)
  → SeaweedFS infra: postgres-backups/dk-data-prod/daily/dk_data_<ts>_daily.dump
    → [NEW] staging-prestaged-restore CronJob (ns dk-data-staging)
         install-mc → mc cp latest daily → sha256 + pg_restore --list gate
         → pg_restore --clean --if-exists --no-owner --no-privileges --no-acl
           --jobs=N -d <staging dk_data>
    → SP3-kept SQLMesh transforms re-derive chembl_activities + pubchem, re-promote
```

SC-005 result: each external source fetched **once** (prod daily), **zero**
in staging.

## The new component

A single staging-only CronJob `staging-prestaged-restore`.

| Aspect | Decision |
|---|---|
| Name | `staging-prestaged-restore` — deliberately ∉ SP3's `^fetch-.*` regex; not a fetcher, never suspended. |
| Image | `ghcr.io/cloudnative-pg/postgresql:16.4` (ships `pg_restore`; same family the backups use). |
| initContainer | `install-mc` — verbatim pattern from `pg-backup-daily` (copy `mc` → `/tmp`). |
| Steps | `mc alias set` prod store `seaweedfs-s3.infra.svc.cluster.local:8333` bucket `postgres-backups` prefix `dk-data-prod/daily/` → latest object via `mc ls … \| tail -1` (verify.sh pattern) → `mc cp` to scratch → sha256 + `pg_restore --list` ≥10-object gate → `pg_restore --clean --if-exists --no-owner --no-privileges --no-acl --jobs=N -d $PG_URL`. |
| Scratch | Dedicated PVC `staging-restore-scratch` (~250 Gi, reclaim Delete) at `/tmp/restore`. **Replaces** the old `prestaged-dk-data` PVC idea (that was for the unused per-source tree). Download-then-restore (not `mc cat \| pg_restore` streaming) to keep the checksum + `--list` integrity gate and `--jobs` parallelism. |
| DB target | Staging Postgres via the staging `dk-data-secrets` DopplerSecret (`stg`) — same `POSTGRES_*` keys the hydrate jobs use. |
| Restore semantics | **In-place** `--clean --if-exists --no-owner --no-privileges --no-acl`. Staging is the explicitly-disposable mirror (SP2 force-resets it to main); no temp-DB-and-swap. Accept brief SQLMesh view/snapshot recreate churn. |
| Schedule | `0 2 * * *` — prod daily starts 12:00 UTC with a 12 h deadline; 02:00 next day clears it. `concurrencyPolicy: Forbid`, `backoffLimit: 1`, `activeDeadlineSeconds: 21600` (6 h). |

## Credentials & overlay wiring (two gotchas)

1. **Prod-store read creds.** The staging overlay repoints
   `minio-backup-credentials` to `infra-staging` — wrong store for reading
   prod's dumps. The CronJob references a **new dedicated DopplerSecret
   `dk-data-prestaged-src-credentials`** (read-only key to prod SeaweedFS
   `postgres-backups`) that the staging overlay does **not** override.
   → operator precondition.
2. **Staging-overlay-only.** The manifest is a new resource listed solely in
   `k8s/overlays/staging/kustomization.yaml` — never in `base/` or `prod/`.
   Prod must not restore from itself.

## Observability (Principle-6-lean, no new exporter)

- Restore writes a breadcrumb row to staging `meta.transform_runs`
  (`details->>'run_label' = 'prestaged-restore-<date>'`, `status`,
  `finished_at`) — the same idempotency table feature-005 uses; queryable in
  Grafana via the existing Postgres datasource.
- `PrometheusRule` alert on
  `kube_job_status_failed{job_name=~"staging-prestaged-restore.*"}` + a stat
  panel on the existing staging dashboard. No bash-pod Prometheus counter.

## Tests (offline, CI-safe — same discipline as the SP1 B002b fix)

1. **Script assertion** (stdlib regex, no cluster): asserts prod
   endpoint/bucket/`dk-data-prod/daily/` prefix, latest-object selection,
   `pg_restore` flag set, target = staging `$POSTGRES_*` (not the staging
   store).
2. **Kustomize render**: `kubectl kustomize k8s/overlays/staging` contains
   `staging-prestaged-restore` (un-suspended, name ∉ `^fetch-.*`);
   `…/prod` and `…/base` do **not**.
3. **Manifest shape** (offline, like the prestaged-hydrate validation):
   apiVersion `batch/v1`, kind `CronJob`, `schedule`, `restartPolicy: Never`,
   image, command.

## Rollback

Delete the one staging-overlay resource line + the manifest (and revert SP3 so
fetchers resume). Instant, staging-only, no data loss (no prod impact;
suspending/un-suspending and restoring are non-destructive to prod).

## Operator preconditions (MUST surface)

1. Create Doppler secret group materialized as
   `dk-data-prestaged-src-credentials` in `dk-data-staging` — **read-only**
   creds to prod SeaweedFS `postgres-backups`.
2. Confirm/allow `dk-data-staging → seaweedfs-s3.infra:8333` egress if a
   default-deny NetworkPolicy exists.
3. ≥ ~250 GB headroom on the staging Postgres instance + the scratch PVC.
4. Merge and green-run this **before** SP3 is ArgoCD-synced to staging, or
   staging raw goes stale between fetcher-suspension and the first restore
   (degraded staging only; reversible).

## Out of scope (YAGNI)

- The per-source `prestaged.py` tree / `k8s/apps/hydrate/` fan-out (prod-only,
  unused by Approach A).
- An automated per-source prestaged producer / S3→PVC sync.
- Weekly-full restore and daily-with-weekly-fallback variants.
- Any change to prod (`base/`, `prod/` overlay) — this is staging-overlay-only.

# Runbook — staging prestaged restore

**What:** staging consumes prod's existing `pg-backup-daily` artifact
instead of re-fetching every external source (WS4 SP3 / feature 211).
Spec: `docs/superpowers/specs/2026-05-19-staging-prestaged-restore-design.md`.

## Operator preconditions (MUST be true before SP3 is ArgoCD-synced)

1. **Source creds.** Doppler `dk-data-applications/prd` has read-only
   keys `SRC_S3_ACCESS_KEY` / `SRC_S3_SECRET_KEY` for prod SeaweedFS
   bucket `postgres-backups`. The `dk-data-prestaged-src-credentials`
   DopplerSecret materialises these into `dk-data-staging`.
2. **Egress.** `dk-data-staging` can reach
   `seaweedfs-s3.infra.svc.cluster.local:8333`. If a default-deny
   NetworkPolicy exists in `dk-data-staging`, add an egress allow to the
   `infra` SeaweedFS service.
3. **Disk.** Staging Postgres has ≥ ~250 GB free for the restored daily
   dataset; the `staging-restore-scratch` PVC requests 250 Gi.
4. **Ordering.** Merge + green-run this restore **before** SP3's
   `^fetch-*` suspension is ArgoCD-synced to staging. Otherwise staging
   raw goes stale between suspension and first restore (degraded
   *staging only*, fully reversible).

## Manual trigger

```
kubectl -n dk-data-staging create job \
  --from=cronjob/staging-prestaged-restore \
  staging-prestaged-restore-$(date +%Y%m%d%H%M)
kubectl -n dk-data-staging logs -f job/staging-prestaged-restore-<ts> -c restore
```

## Verify

```
psql ... -c "SELECT status, ended_at, details->>'object'
             FROM meta.transform_runs
             WHERE procedure_name='staging-prestaged-restore'
             ORDER BY ended_at DESC LIMIT 5;"
```

Dashboard: **dk-data Staging Prestaged Restore**
(`uid=dk-data-fe-staging-prestaged-restore`).
Alerts: `grafana/alerts/staging-prestaged-restore.yaml` (apply by hand,
mirrors the `gold-zero-rows.yaml` convention).

## Rollback (resume staging fetchers)

1. Delete the `staging-prestaged-restore.yaml` line from
   `k8s/overlays/staging/kustomization.yaml`.
2. Revert the SP3 `^fetch-*` suspend patch in the same file.

Instant, staging-only, no data loss (prod untouched throughout).

# Kubernetes Job Contract: `prestaged-hydrate`

## Manifest location

`deploy/jobs/prestaged-hydrate.yaml`

## Shape

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: prestaged-hydrate-<date>
  namespace: dk-data-prod
spec:
  backoffLimit: 0        # re-run is a human decision; see FR-011 idempotency
  ttlSecondsAfterFinished: 604800   # 7 days
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: hydrate
          image: ghcr.io/datakinetic/dk-data:prod-<sha>   # must include postgresql-client-16
          command: ["python","-m","dk_data.ingestion.prestaged","--source-list","all"]
          env:
            - name: PRESTAGED_ROOT
              value: /data/prestaged
            - name: PG_URL
              valueFrom: { secretKeyRef: { name: dk-data-db, key: url } }
            - name: WAL_PAUSE_HIGH_PCT
              value: "70"
            - name: WAL_PAUSE_LOW_PCT
              value: "40"
          resources:
            requests: { cpu: 500m, memory: 512Mi }
            limits:   { cpu: 2,    memory: 4Gi  }
          volumeMounts:
            - name: prestaged
              mountPath: /data/prestaged
              readOnly: true
      volumes:
        - name: prestaged
          # While MinIO is down: hostPath on k3s-master-1
          hostPath:
            path: /opt/dk-data-prestaged
            type: Directory
          # After MinIO returns: swap to PVC (no code change in the container)
          # persistentVolumeClaim:
          #   claimName: prestaged-dk-data
```

## Liveness / readiness

No probes — Job, not Deployment.

## Re-run procedure

```
kubectl -n dk-data-prod create job --from=cronjob/prestaged-hydrate prestaged-hydrate-$(date +%Y%m%d%H%M)
```

The deterministic `run_id` (R4) means a re-run on the same inventory is a no-op (SC-006).

## Image requirements

- Base: existing `dk-data` image from `pyproject.toml`
- Added apt package: `postgresql-client-16` (for `pg_restore`)
- No other additions

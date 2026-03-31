# Quickstart: Verify Post-Deployment Fixes

**Branch**: `021-post-deploy-fixes`

---

## 1. Verify EPO Credentials Are Live in Cluster

After merging `021` to main and promoting the image, confirm EPO keys synced:

```bash
# Check Doppler has real values (not CHANGEME)
doppler secrets get EPO_CONSUMER_KEY EPO_CONSUMER_SECRET \
  --project dk-data-applications --config prd

# Verify sync reached cluster (wait up to 5 minutes after Doppler update)
kubectl get secret dk-data-secrets -n dk-data-prod -o jsonpath='{.data.EPO_CONSUMER_KEY}' \
  | base64 -d | wc -c
# Expected: > 20 chars (real key, not CHANGEME placeholder)
```

---

## 2. Verify DDInter CronJob Was Pruned

```bash
kubectl get cronjob -n dk-data-prod | grep ddinter
# Expected: no output
```

---

## 3. Manually Trigger EPO Fetch to Confirm Fix

```bash
kubectl create job --from=cronjob/fetch-epo fetch-epo-test -n dk-data-prod
kubectl logs -f job/fetch-epo-test -n dk-data-prod
# Expected: OAuth token acquired, patent records inserted
# Not expected: "401 Unauthorized" or "EPO_CONSUMER_KEY not set"
```

---

## 4. Verify All CHANGEME Keys Are Gone

```bash
doppler secrets --project dk-data-applications --config prd \
  | grep CHANGEME
# Expected: no output
```

Currently remaining (blocked externally):
- `USPTO_API_KEY` — tracked in issue #170
- `USPTO_TSDR_API_KEY` — tracked in issue #170

---

## 5. Verify Graceful Skip for Missing USPTO Keys

```bash
kubectl create job --from=cronjob/fetch-uspto-patents fetch-uspto-test -n dk-data-prod
kubectl logs -f job/fetch-uspto-patents-test -n dk-data-prod
# Expected: "source_unavailable" status, exit 0, WARNING log
# Not expected: pod failure (exit 1) or exception traceback
```

---

## 6. HCS Pipeline Status (Separate Action Required)

The HCS bronze/silver transformation pipeline has not been initialised. To populate it:

```bash
# Apply the one-time backfill job (WARNING: takes 4-12 hours)
kubectl apply -f k8s/apps/cronjobs/base/job-initial-backfill.yaml -n dk-data-prod
kubectl logs -f job/initial-backfill -n dk-data-prod

# Cleanup after completion
kubectl delete job initial-backfill -n dk-data-prod
```

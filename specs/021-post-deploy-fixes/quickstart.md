# Quickstart: Verify Post-Deployment Fixes

**Branch**: `021-post-deploy-fixes`

---

## 1. Verify EPO Credentials Are Live in Cluster

```bash
# Check Doppler has real values (not CHANGEME)
doppler secrets get EPO_CONSUMER_KEY EPO_CONSUMER_SECRET \
  --project dk-data-applications --config prd

# Verify sync reached cluster (wait up to 5 minutes after Doppler update)
kubectl get secret dk-data-secrets -n dk-data-prod \
  -o jsonpath='{.data.EPO_CONSUMER_KEY}' | base64 -d | wc -c
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
doppler secrets --project dk-data-applications --config prd | grep CHANGEME
# Expected: no output (USPTO keys remain CHANGEME — tracked in issue #170)
```

---

## 5. Verify Graceful Skip for Missing USPTO Keys

```bash
kubectl create job --from=cronjob/fetch-uspto-patents fetch-uspto-test -n dk-data-prod
kubectl logs -f job/fetch-uspto-patents-test -n dk-data-prod
# Expected: "source_unavailable" status, exit 0, WARNING log
```

---

## 6. Verify WHO ICD Fetcher Uses Live Endpoints

```bash
# Test ICD-10 dynamic discovery (requires WHO_ICD_CLIENT_ID + CLIENT_SECRET in env)
python3 -c "
from dk_data.ingestion.fetchers.who_icd import WHOICDFetcher
f = WHOICDFetcher()
chapters = f._discover_top_chapters('https://id.who.int/icd/release/10/2019')
print(f'ICD-10 chapters discovered: {len(chapters)}')
# Expected: > 0 (typically 22 chapters in ICD-10)
"

# Confirm dead URL is gone from codebase
grep -r "apps.who.int" src/dk_data/ingestion/fetchers/
# Expected: no output
```

---

## 7. Verify SQL Model Grain Integrity

```bash
# Check DISTINCT ON is present in all grain-critical silver models
grep -l "DISTINCT ON" \
  src/dk_data/sqlmesh/models/hcs/silver/cms_formulary.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_pecos.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_dmepos.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_chow.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_hospital_affiliation.sql \
  src/dk_data/sqlmesh/models/molecules/silver/imgt.sql \
  src/dk_data/sqlmesh/models/molecules/silver/cochrane_reviews.sql \
  src/dk_data/sqlmesh/models/molecules/silver/nice_hta.sql \
  src/dk_data/sqlmesh/models/molecules/silver/ttd.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_ndc.sql
# Expected: all 10 files listed

# Confirm processed_to_silver filter is gone from patent_exclusivities
grep "processed_to_silver" \
  src/dk_data/sqlmesh/models/molecules/silver/patent_exclusivities.sql
# Expected: only comments (lines starting with --), no WHERE clause

# Confirm mol_silver.healthcare_facilities is deleted
ls src/dk_data/sqlmesh/models/molecules/silver/healthcare_facilities.sql 2>&1
# Expected: "No such file or directory"

# Confirm epidemiology.sql exists (renamed from indication_epidemiology.sql)
ls src/dk_data/sqlmesh/models/ind/silver/epidemiology.sql
# Expected: file found

ls src/dk_data/sqlmesh/models/ind/silver/indication_epidemiology.sql 2>&1
# Expected: "No such file or directory"
```

---

## 8. Verify New Silver Models Exist

```bash
ls \
  src/dk_data/sqlmesh/models/hcs/silver/cms_cost_reports_puf_lines.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_hospital_info.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_physician_puf_services.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_post_acute.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_stabilis.sql \
  src/dk_data/sqlmesh/models/hcs/silver/cms_usp.sql \
  src/dk_data/sqlmesh/models/molecules/silver/ema_regulatory_docs.sql
# Expected: all 7 files listed
```

---

## 9. Verify Backfill Retry and Metrics

```bash
# Confirm retry import is present
grep "retry_with_backoff" src/dk_data/ingestion/initial_backfill.py
# Expected: import line + decorator in _fetch_one

# Confirm per-source success metric is emitted
grep "mark_job_success.*backfill_fetch" src/dk_data/ingestion/initial_backfill.py
# Expected: mark_job_success(f'backfill_fetch_{source}')

# Confirm Prometheus server is started in main.py
grep "_prom_start_http_server" src/dk_data/ingestion/main.py
# Expected: _prom_start_http_server(8000) call in main()

# Confirm batch_size is in _INTERNAL_KWARGS
grep "batch_size" src/dk_data/ingestion/main.py | grep "INTERNAL"
# Expected: 'batch_size' in the set
```

---

## 10. HCS Pipeline Status (Separate Action Required)

The HCS bronze/silver transformation pipeline has not been initialised. To populate it:

```bash
# Apply the one-time backfill job (WARNING: takes 4-12 hours)
kubectl apply -f k8s/apps/cronjobs/base/job-initial-backfill.yaml -n dk-data-prod
kubectl logs -f job/initial-backfill -n dk-data-prod

# Cleanup after completion
kubectl delete job initial-backfill -n dk-data-prod
```

---

## 11. Run Tests

```bash
# Run the test suite (from repo root)
cd src && pytest -x -q
# Expected: all tests pass

# Lint check
ruff check .
# Expected: no errors
```

# Quickstart: Admin App Integration Fix Verification

**Feature**: 006-006-admin-integration
**Date**: 2026-02-01

## Prerequisites

- `kubectl` configured with dk-alchemy cluster access
- Access to both `dk-data-staging` and `dk-data-prod` namespaces
- Valid JWT token for authenticated endpoint testing

## Quick Status Check

```bash
# Check current cluster state
kubectl get pods -n dk-data-prod
kubectl get pods -n dk-data-staging

# Check PostgREST relation count (should be > 0)
kubectl logs -n dk-data-staging -l app=postgrest --tail=5 | grep "Relations"
kubectl logs -n dk-data-prod -l app=postgrest --tail=5 | grep "Relations"
```

## Phase A: Verify db-init Fix

### A.1 Check db-init Job Status

```bash
# Staging
kubectl get jobs -n dk-data-staging
kubectl logs -n dk-data-staging job/db-init --tail=100

# Production
kubectl get jobs -n dk-data-prod
kubectl logs -n dk-data-prod job/db-init --tail=100
```

**Expected Output** (no errors):
```
=== dk-data database initialization ===
Host: postgresql.infra.svc.cluster.local:5432
Creating database dk_data if not exists...
Creating extensions...
Creating schemas...
Creating roles...
✓ All 5 roles created successfully
✓ All 12 schemas created successfully
✓ Found N API views
=== Database initialization complete ===
```

### A.2 Verify Roles Created

```bash
# Connect to database and check roles
kubectl run db-check -n dk-data-staging --rm -it --restart=Never \
  --image=postgres:16.4 \
  --env="PGPASSWORD=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)" \
  --env="PGHOST=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_HOST}' | base64 -d)" \
  -- psql -U postgres -d dk_data -c "SELECT rolname FROM pg_roles WHERE rolname IN ('authenticator', 'web_anon', 'analyst', 'api_user', 'readonly') ORDER BY rolname;"
```

**Expected Output**:
```
    rolname
----------------
 analyst
 api_user
 authenticator
 readonly
 web_anon
(5 rows)
```

### A.3 Verify Schemas Created

```bash
kubectl run db-check -n dk-data-staging --rm -it --restart=Never \
  --image=postgres:16.4 \
  --env="PGPASSWORD=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)" \
  --env="PGHOST=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_HOST}' | base64 -d)" \
  -- psql -U postgres -d dk_data -c "SELECT nspname FROM pg_namespace WHERE nspname IN ('raw', 'staging', 'mart', 'scoring', 'meta', 'api', 'mol_raw', 'mol_bronze', 'mol_silver', 'mol_gold', 'mol_app', 'mol_api') ORDER BY nspname;"
```

**Expected Output**: 12 schemas listed

## Phase B: Verify PostgREST Recovery

### B.1 Check Pod Status

```bash
# All pods should show 1/1 Running with low restart count
kubectl get pods -n dk-data-prod -l app=postgrest
```

**Expected Output**:
```
NAME                         READY   STATUS    RESTARTS   AGE
postgrest-xxxxxxxxxx-xxxxx   1/1     Running   0          XXm
postgrest-xxxxxxxxxx-xxxxx   1/1     Running   0          XXm
postgrest-xxxxxxxxxx-xxxxx   1/1     Running   0          XXm
```

### B.2 Check PostgREST Schema Cache

```bash
kubectl logs -n dk-data-staging deploy/postgrest --tail=10 | grep "Schema cache"
```

**Expected Output**:
```
Schema cache loaded X Relations, X Relationships, X Functions
```

Where X Relations >= 8 (5 original + 3 new Compass views)

### B.3 Test Health Endpoint

```bash
# Port forward to test locally
kubectl port-forward -n dk-data-staging svc/postgrest 3030:3000 &
PF_PID=$!
sleep 2

# Test health endpoint (should work without auth)
curl -s http://localhost:3030/health | jq .

# Cleanup
kill $PF_PID
```

**Expected Output**:
```json
[{"status":"ok","timestamp":"2026-02-01T...","database":"dk_data"}]
```

## Phase C: Verify Compass API Views

### C.1 List Available Views

```bash
kubectl run db-check -n dk-data-staging --rm -it --restart=Never \
  --image=postgres:16.4 \
  --env="PGPASSWORD=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)" \
  --env="PGHOST=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_HOST}' | base64 -d)" \
  -- psql -U postgres -d dk_data -c "SELECT schemaname, viewname FROM pg_views WHERE schemaname = 'api' ORDER BY viewname;"
```

**Expected Output**:
```
 schemaname |    viewname
------------+------------------
 api        | data_catalog
 api        | data_sources
 api        | health
 api        | molecules        <- NEW
 api        | resolution_queue <- NEW
 api        | scoring
 api        | targets
(7+ rows)
```

### C.2 Test Molecules Endpoint (Authenticated)

```bash
# Get JWT token (example - adjust for your auth setup)
JWT_TOKEN="your-jwt-token-here"

kubectl port-forward -n dk-data-staging svc/postgrest 3030:3000 &
PF_PID=$!
sleep 2

# Test molecules endpoint with auth
curl -s -H "Authorization: Bearer $JWT_TOKEN" http://localhost:3030/molecules | jq .

kill $PF_PID
```

**Expected Output**: Empty array `[]` (placeholder view) or molecule data

### C.3 Test Resolution Queue Access Control

```bash
kubectl port-forward -n dk-data-staging svc/postgrest 3030:3000 &
PF_PID=$!
sleep 2

# Anonymous access should be denied
curl -s http://localhost:3030/resolution_queue | jq .
# Expected: Permission denied error

# Authenticated access should work
curl -s -H "Authorization: Bearer $JWT_TOKEN" http://localhost:3030/resolution_queue | jq .
# Expected: Empty array or queue data

kill $PF_PID
```

## Troubleshooting

### db-init Job Failed

```bash
# Check job logs
kubectl logs -n dk-data-prod job/db-init

# Delete and recreate job
kubectl delete job db-init -n dk-data-prod
kubectl apply -k k8s/overlays/prod

# Watch for completion
kubectl get jobs -n dk-data-prod -w
```

### PostgREST CrashLoopBackOff

```bash
# Check pod logs
kubectl logs -n dk-data-prod -l app=postgrest --tail=50

# If due to missing views, fix db-init first
# Then restart PostgREST
kubectl rollout restart deployment/postgrest -n dk-data-prod
```

### Schema Not Loaded

```bash
# Force PostgREST to reload schema
kubectl exec -n dk-data-staging deploy/postgrest -- kill -HUP 1

# Check logs for reload
kubectl logs -n dk-data-staging deploy/postgrest --tail=20
```

### Permission Denied Errors

```bash
# Check role grants
kubectl run db-check -n dk-data-staging --rm -it --restart=Never \
  --image=postgres:16.4 \
  --env="PGPASSWORD=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)" \
  --env="PGHOST=$(kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.POSTGRES_HOST}' | base64 -d)" \
  -- psql -U postgres -d dk_data -c "
    SELECT grantee, privilege_type, table_schema, table_name
    FROM information_schema.role_table_grants
    WHERE table_schema = 'api'
    ORDER BY table_name, grantee;"
```

## Admin App Verification

Once dk-data is fixed, verify Admin App integration:

1. **Compass Search Page**: Should load without 503 errors
2. **Data Sources**: Should display (possibly empty) data sources list
3. **Status Indicator**: If implemented, should show "dk-data: online"

```bash
# Test from Admin App environment
curl -H "Authorization: Bearer $ADMIN_JWT" https://dk-data-staging.behaviorlabs.ai/molecules
curl -H "Authorization: Bearer $ADMIN_JWT" https://dk-data-staging.behaviorlabs.ai/data_sources
```

## Success Criteria

- [ ] db-init Job exits with code 0
- [ ] All 5 roles exist in pg_roles
- [ ] All 12 schemas exist in pg_namespace
- [ ] PostgREST loads 8+ Relations
- [ ] All PostgREST pods are Running with 0 restarts
- [ ] `/health` returns 200 OK
- [ ] `/molecules` accessible with JWT
- [ ] `/resolution_queue` denied for anonymous, allowed for analyst
- [ ] Admin App Compass pages load without 503 errors

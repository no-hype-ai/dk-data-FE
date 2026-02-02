# dk-data Admin App Integration: Analysis and Recommendations

**Date**: 2026-02-02
**Context**: Behavior Labs Admin App integration with dk-data PostgREST API
**Source**: `/Users/nicholas/Code/behavior-labs-ai/ADMIN_APP_ISSUES.md`

---

## Executive Summary

The Behavior Labs Admin App is experiencing 503 errors when accessing Compass features due to dk-data integration issues. This document provides a comprehensive analysis of the root causes and detailed recommendations for resolution.

### Critical Findings

| Environment | Status | Root Cause |
|-------------|--------|------------|
| **Production** | CRITICAL | db-init job failed - 0 Relations loaded, roles don't exist |
| **Staging** | DEGRADED | API views exist but some SQL errors, HTTP probes working |
| **Admin App** | BLOCKED | Expects views that don't exist (`molecules`, `resolution_queue`) |

---

## 1. Cluster State Analysis

### 1.1 Production Environment (`dk-data-prod`)

**Observed Issues:**
```
postgrest-68577ffbbc-xvtkl   0/1     CrashLoopBackOff   472 restarts
postgrest-6ff6d9454f-*       1/1     Running            (0 Relations)
```

**PostgREST Logs (All Pods):**
```
Schema cache loaded 0 Relations, 0 Relationships, 0 Functions
```

**db-init Job Logs (FAILED):**
```
ERROR:  role "readonly" does not exist
ERROR:  role "web_anon" does not exist
ERROR:  role "analyst" does not exist
ERROR:  role "api_user" does not exist
ERROR:  syntax error at or near "$"
```

**Root Causes:**
1. **Heredoc Escaping Bug**: The `DO $$...$$` PL/pgSQL blocks are not being escaped correctly in the bash heredoc
2. **Role Creation Failed**: Without roles, all subsequent grants fail silently
3. **View Creation Failed**: No API views exist in production
4. **CrashLoopBackOff**: New pods with HTTP health probes fail because `/health` view doesn't exist

### 1.2 Staging Environment (`dk-data-staging`)

**Observed Status:**
```
postgrest-649bc5c854-*   1/1   Running   (5 Relations)
```

**PostgREST Logs:**
```
Schema cache loaded 5 Relations, 0 Relationships, 0 Functions
```

**db-init Verification:**
```
✓ All 5 roles created successfully
✓ All 12 schemas created successfully
✓ Found 5 API views
```

**Available Views:**
- `api.health` - Health check endpoint
- `api.data_catalog` - Table metadata
- `api.targets` - Placeholder (empty)
- `api.scoring` - Placeholder (empty)
- `api.data_sources` - Placeholder (empty)

**Remaining SQL Errors:**
```
ERROR: syntax error at or near "$" (cross-database isolation section)
```

### 1.3 Admin App Expected Endpoints

Based on `ADMIN_APP_ISSUES.md`, the Compass features expect:

| Expected View | Current Status | Notes |
|---------------|----------------|-------|
| `molecules` | **MISSING** | Core molecule search functionality |
| `data_sources` | EXISTS (placeholder) | Needs real implementation |
| `resolution_queue` | **MISSING** | Molecule resolution workflow |

---

## 2. Root Cause Deep Dive

### 2.1 db-init Heredoc Escaping Issue

The current `db-init-job.yaml` uses bash heredocs with PL/pgSQL `DO $$...$$` blocks. The escaping is incorrect.

**Current Code (Broken):**
```bash
psql -d dk_data <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (...) THEN
    CREATE ROLE authenticator LOGIN NOINHERIT;
  END IF;
END $$;
SQL
```

**Problem**: When this runs through kubectl exec, the `$$` delimiters get interpreted incorrectly by various shell layers.

**Evidence from Logs:**
```
ERROR: syntax error at or near "$"
LINE 1: DO $
           ^
```

### 2.2 Cross-Database Isolation Bug

The cross-database isolation section has a more complex escaping issue:

**Current Code (Broken):**
```bash
psql -d postgres <<'SQL'
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'behavior_labs') THEN
    EXECUTE 'REVOKE CONNECT ON DATABASE behavior_labs FROM authenticator';
  END IF;
END $$;
SQL
```

**Error:**
```
ERROR: syntax error at or near "'REVOKE CONNECT..."
```

**Cause**: The single quotes inside `EXECUTE '...'` are being mangled during heredoc processing.

### 2.3 Admin App View Mismatch

The Admin App's Compass features expect a specific schema:

```typescript
// apps/admin/lib/compass/postgrest-client.ts
const ENDPOINTS = {
  search: '/molecules',        // MISSING
  sources: '/data_sources',    // EXISTS but placeholder
  resolution: '/resolution_queue'  // MISSING
};
```

The current dk-data implementation provides different views focused on hospital targeting data, not molecule discovery.

---

## 3. Recommendations

### 3.1 CRITICAL: Fix Production db-init (P0)

**Action**: Rerun db-init with corrected SQL escaping

**Option A: Inline SQL Commands (Recommended)**

Replace heredoc PL/pgSQL blocks with individual `psql -c` commands:

```yaml
# k8s/base/db-init-job.yaml (excerpt)
command:
  - /bin/bash
  - -c
  - |
    set -euo pipefail

    # Create roles using DO blocks with proper escaping
    psql -d dk_data -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN CREATE ROLE authenticator LOGIN NOINHERIT; END IF; END \$\$;"
    psql -d dk_data -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_anon') THEN CREATE ROLE web_anon NOLOGIN; END IF; END \$\$;"
    psql -d dk_data -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN CREATE ROLE analyst NOLOGIN; END IF; END \$\$;"
    psql -d dk_data -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN CREATE ROLE api_user NOLOGIN; END IF; END \$\$;"
    psql -d dk_data -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN CREATE ROLE readonly LOGIN; END IF; END \$\$;"
```

**Option B: External SQL File**

Mount a ConfigMap containing the SQL script:

```yaml
volumes:
  - name: init-scripts
    configMap:
      name: db-init-scripts
containers:
  - name: db-init
    command:
      - /bin/bash
      - -c
      - psql -d dk_data -f /scripts/init.sql
    volumeMounts:
      - name: init-scripts
        mountPath: /scripts
```

**Immediate Action for Production:**

```bash
# Delete failed job and recreate
kubectl delete job db-init -n dk-data-prod
kubectl apply -k k8s/overlays/prod

# Or run manual initialization
kubectl run db-fix -n dk-data-prod --rm -it --restart=Never \
  --image=postgres:16.4 \
  --env=PGPASSWORD=$(kubectl get secret dk-data-secrets -n dk-data-prod -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d) \
  --env=PGHOST=$(kubectl get secret dk-data-secrets -n dk-data-prod -o jsonpath='{.data.POSTGRES_HOST}' | base64 -d) \
  -- bash -c '
    psql -U postgres -d dk_data -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '\''authenticator'\'') THEN CREATE ROLE authenticator LOGIN NOINHERIT; END IF; END \$\$;"
    # ... additional role and view creation
  '
```

### 3.2 HIGH: Fix CrashLoopBackOff Pod (P1)

**Issue**: Pod `postgrest-68577ffbbc-xvtkl` has HTTP health probe but no `/health` view exists

**Root Cause**: ArgoCD sync created pod with new HTTP probe configuration before db-init was fixed

**Resolution Options:**

1. **Fix db-init first** (Recommended) - Once views exist, pod will become healthy
2. **Delete the crashing pod** - Let the healthy ReplicaSet manage all pods:
   ```bash
   kubectl delete pod postgrest-68577ffbbc-xvtkl -n dk-data-prod
   ```
3. **Scale down new ReplicaSet temporarily**:
   ```bash
   kubectl scale rs postgrest-68577ffbbc -n dk-data-prod --replicas=0
   ```

### 3.3 HIGH: Add Compass-Required Views (P1)

Create the views the Admin App expects:

```sql
-- api.molecules: Molecule search and discovery
CREATE OR REPLACE VIEW api.molecules AS
SELECT
  m.id,
  m.smiles,
  m.inchi_key,
  m.name,
  m.molecular_weight,
  m.created_at,
  m.updated_at
FROM mol_gold.molecules m
WHERE m.is_active = true;

GRANT SELECT ON api.molecules TO web_anon, analyst, api_user;

-- api.resolution_queue: Pending molecule resolutions
CREATE OR REPLACE VIEW api.resolution_queue AS
SELECT
  r.id,
  r.source_id,
  r.target_smiles,
  r.status,
  r.priority,
  r.created_at,
  r.resolved_at
FROM mol_app.resolution_queue r
WHERE r.status != 'completed';

GRANT SELECT ON api.resolution_queue TO analyst, api_user;
-- Note: web_anon should NOT have access to resolution queue

-- api.data_sources: Enhanced with real data
CREATE OR REPLACE VIEW api.data_sources AS
SELECT
  s.id,
  s.name,
  s.source_type,
  s.last_fetch_at,
  s.status,
  s.record_count,
  s.error_message
FROM mol_app.data_sources s
ORDER BY s.last_fetch_at DESC;

GRANT SELECT ON api.data_sources TO web_anon, analyst, api_user;
```

### 3.4 MEDIUM: Admin App Graceful Degradation (P2)

Update the Admin App to handle dk-data unavailability gracefully:

**File**: `apps/admin/lib/compass/postgrest-client.ts`

```typescript
export class PostgRESTClient {
  private baseUrl: string;
  private healthCheckCache: { status: boolean; timestamp: number } | null = null;
  private readonly HEALTH_CACHE_TTL = 30000; // 30 seconds

  async isAvailable(): Promise<boolean> {
    // Check cache first
    if (this.healthCheckCache &&
        Date.now() - this.healthCheckCache.timestamp < this.HEALTH_CACHE_TTL) {
      return this.healthCheckCache.status;
    }

    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      });
      const status = response.ok;
      this.healthCheckCache = { status, timestamp: Date.now() };
      return status;
    } catch {
      this.healthCheckCache = { status: false, timestamp: Date.now() };
      return false;
    }
  }

  async searchMolecules(query: string): Promise<SearchResult> {
    if (!await this.isAvailable()) {
      return {
        status: 'unavailable',
        message: 'Molecule database is currently unavailable',
        results: [],
      };
    }
    // ... existing search logic
  }
}
```

**File**: `apps/admin/components/compass/service-status.tsx`

```typescript
'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@repo/design-system/components/ui/badge';

export function CompassServiceStatus() {
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking');

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch('/api/compass/health');
        setStatus(res.ok ? 'online' : 'offline');
      } catch {
        setStatus('offline');
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const variants = {
    checking: 'secondary',
    online: 'default',
    offline: 'destructive',
  } as const;

  return (
    <Badge variant={variants[status]}>
      dk-data: {status}
    </Badge>
  );
}
```

### 3.5 LOW: Fix Cross-Database Isolation (P3)

The cross-database isolation section has escaping issues. Since this is optional security hardening:

**Option A: Remove for now**
```yaml
# Comment out until properly tested
# --- Step 11: Cross-database isolation ---
# echo "Enforcing cross-database isolation..."
# (skipped)
```

**Option B: Fix with proper escaping**
```bash
# Use dollar-quoting with different tags
psql -d postgres -c "
DO \$iso\$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'behavior_labs') THEN
    EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM authenticator', 'behavior_labs');
  END IF;
END \$iso\$;
"
```

---

## 4. Implementation Priority

### Phase 1: Emergency Production Fix (Immediate)

1. Run manual db-init commands to create roles and views in production
2. Delete crashing pod to stop restart loop
3. Verify PostgREST loads 5 Relations
4. Confirm `/health` endpoint responds with 200

### Phase 2: db-init Code Fix (Today)

1. Update `k8s/base/db-init-job.yaml` with proper escaping
2. Test locally with docker-compose
3. PR to staging, verify ArgoCD sync
4. PR to main after staging validation

### Phase 3: Compass Views (This Week)

1. Design molecule search schema
2. Create `api.molecules` and `api.resolution_queue` views
3. Update Admin App PostgREST client configuration
4. Add service status indicator to Compass pages

### Phase 4: Resilience (Next Sprint)

1. Implement graceful degradation in Admin App
2. Add circuit breaker for dk-data calls
3. Configure proper timeouts and retries
4. Add monitoring/alerting for dk-data availability

---

## 5. Monitoring Recommendations

### 5.1 Add PostgREST Metrics

```yaml
# k8s/base/postgrest/deployment.yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "3000"
  prometheus.io/path: "/live"
```

### 5.2 Alert Rules

```yaml
# k8s/base/alert-rules.yaml
- alert: PostgRESTZeroRelations
  expr: postgrest_schema_cache_relations_total == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "PostgREST has no relations loaded"
    description: "PostgREST instance {{ $labels.pod }} has 0 relations. Database views may be missing."

- alert: PostgRESTHealthCheckFailing
  expr: probe_success{job="postgrest-health"} == 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "PostgREST health endpoint failing"
```

### 5.3 Dashboard Queries

```promql
# PostgREST request latency
histogram_quantile(0.95, rate(postgrest_request_duration_seconds_bucket[5m]))

# Relations loaded (should be > 0)
postgrest_schema_cache_relations_total

# Error rate
rate(postgrest_requests_total{status=~"5.."}[5m])
```

---

## 6. Quick Reference Commands

### Check Production Status
```bash
# Pod status
kubectl get pods -n dk-data-prod

# PostgREST logs
kubectl logs -n dk-data-prod -l app=postgrest --tail=50

# Test health endpoint
kubectl port-forward -n dk-data-prod svc/postgrest 3030:3000 &
curl http://localhost:3030/health
```

### Fix Production Manually
```bash
# Run db-init manually
kubectl run db-fix -n dk-data-prod --rm -it --restart=Never \
  --image=postgres:16.4 \
  --env="PGPASSWORD=$(kubectl get secret dk-data-secrets -n dk-data-prod -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)" \
  --env="PGHOST=$(kubectl get secret dk-data-secrets -n dk-data-prod -o jsonpath='{.data.POSTGRES_HOST}' | base64 -d)" \
  --env="PGPORT=$(kubectl get secret dk-data-secrets -n dk-data-prod -o jsonpath='{.data.POSTGRES_PORT}' | base64 -d)" \
  -- psql -U postgres -d dk_data

# Inside psql, run role creation and view creation SQL
```

### Restart PostgREST
```bash
# Force schema reload
kubectl exec -n dk-data-prod deploy/postgrest -- kill -HUP 1

# Or rollout restart
kubectl rollout restart deployment/postgrest -n dk-data-prod
```

---

## 7. Appendix: Full db-init Fix

See separate file: `k8s/base/db-init-job-fixed.yaml` (to be created)

Key changes:
1. Use `\$\$` escaping for DO blocks
2. Use individual `psql -c` commands instead of heredocs for complex SQL
3. Add proper error handling with `set -e`
4. Add verification queries after each step

---

*Document generated by Claude Code analysis of cluster state and Admin App integration requirements.*

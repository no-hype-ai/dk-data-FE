# dk-data-fe Platform Review & Recommendations

**Date:** 2026-02-14
**Reviewer:** Claude Opus 4.6
**Scope:** GitHub issues, Kubernetes deployment (Proxmox k3d cluster), codebase deep review

---

## Executive Summary

dk-data-fe is a data platform for TAVR hospital targeting and pharmaceutical molecule lifecycle intelligence, built on PostgreSQL 16 + PostgREST 12.2.3 + FastAPI + SQLMesh. The platform has a solid architectural foundation but is currently **partially operational**: PostgREST is healthy and serving the API, but **all ingestion pipelines are broken** due to missing container registry credentials and DNS resolution failures in the k3d cluster. There are 50 open GitHub issues spanning security, infrastructure, data sources, and code quality -- approximately 15 of which are already resolved in code and should be closed.

### Health at a Glance

| Component | Status | Details |
|-----------|--------|---------|
| PostgREST API (staging) | **Healthy** | 2/2 replicas, 7 relations loaded |
| PostgREST API (prod) | **Healthy** | 3/3 replicas, serving correctly |
| Job Trigger (staging) | **Broken** | ImagePullBackOff -- image cannot be pulled |
| Job Trigger (prod) | **Scaled to 0** | Intentionally disabled, but uses wrong image tag |
| CronJobs (both) | **All Failing** | 5/5 CronJobs in DeadlineExceeded state |
| Database (infra) | **Healthy** | PostgreSQL 16.11, shared cluster running |
| Ingress/TLS | **Working** | Let's Encrypt TLS, Traefik rate limiting |
| CI/CD Pipeline | **Working** | GitHub Actions builds images on push |

---

## 1. Critical Issues (Fix Immediately)

### 1.1 Missing `ghcr-credentials` Secret -- All Ingestion Broken

**Severity:** CRITICAL
**Impact:** Job-trigger deployment and all 5 CronJobs fail in both staging and production
**Evidence:** Pod events show `Unable to retrieve some image pull secrets (ghcr-credentials)` and `ImagePullBackOff`

The `ghcr-credentials` Kubernetes secret does not exist in `dk-data-staging` or `dk-data-prod`, yet `job-trigger-deployment.yaml:23-24` references it. The CI/CD pipeline (`.github/workflows/build-push.yaml`) correctly pushes images to `ghcr.io/data-kinetic/dk-data-fe/job-trigger`, but pods can't authenticate to pull them.

**Recommendation:**
```bash
# Create in both namespaces
for NS in dk-data-staging dk-data-prod; do
  kubectl create secret docker-registry ghcr-credentials \
    --docker-server=ghcr.io \
    --docker-username=<GITHUB_USERNAME> \
    --docker-password=<GITHUB_PAT_WITH_PACKAGES_READ> \
    -n $NS
done
```

Consider managing this through Doppler or a sealed-secret to avoid manual rotation.

### 1.2 DNS Resolution Failure in k3d Cluster

**Severity:** CRITICAL
**Impact:** Even with valid credentials, image pulls fail: `dial tcp: lookup ghcr.io: no such host`
**Root Cause:** k3d cluster networking -- CoreDNS cannot resolve external hostnames from within the cluster

**Recommendation:**
- Verify k3d DNS forwarding: `kubectl -n kube-system get configmap coredns -o yaml`
- Check if the host Docker network allows DNS forwarding (common k3d issue on macOS)
- Quick fix: add `--k3s-arg '--resolv-conf=/run/systemd/resolve/resolv.conf@server:0'` to k3d cluster config, or configure CoreDNS to forward to `8.8.8.8`
- Alternative: pre-load images locally with `k3d image import <image>` to bypass external pulls entirely

### 1.3 Hardcoded Credential in `init_database.sql`

**Severity:** HIGH
**Location:** `src/dk_data/sql/init_database.sql:413`
**Finding:** `CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'postgrest_secret_change_me'`

This default password is checked into source control. If this SQL ever runs in production without override, PostgREST's database authenticator role would have a well-known password.

**Recommendation:**
- Replace with a parameterized approach: `CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD :'AUTHENTICATOR_PASSWORD';`
- Pass the password via `psql -v AUTHENTICATOR_PASSWORD="$REAL_SECRET"` in the db-init job
- Add a pre-flight check that rejects the default value

### 1.4 No Database Backup Strategy (Issue #13)

**Severity:** P0 CRITICAL
**Impact:** Total data loss from hardware failure, human error, or corruption. No PITR, no automated backups, no offsite replication.

**Recommendation:**
- **Immediate**: Add a pg_dump CronJob that writes to a PVC or MinIO (MinIO is already running in the infra namespace)
- **Short-term**: Enable CloudNativePG continuous archiving to the existing MinIO instance with WAL-G
- **Verify**: Schedule weekly backup restoration tests to a temporary database

### 1.5 Database Name Configuration Drift

**Severity:** HIGH
**Impact:** Local dev uses `edwards_tavr`, CI tests use `dk_data_test`, Kubernetes uses `dk_data` (via Doppler secrets). The init SQL has `\connect edwards_tavr` hardcoded.

**Locations:**
- `docker-compose.yml:40` -- `POSTGRES_DB: "${POSTGRES_DB:-edwards_tavr}"`
- `src/dk_data/sql/init_database.sql:8` -- `\connect edwards_tavr`
- `.github/workflows/ci.yaml:41` -- `POSTGRES_DB: dk_data_test`
- K8s secrets (Doppler) -- `dk_data`

**Recommendation:**
- Standardize on `dk_data` everywhere
- Remove `\connect edwards_tavr` from init SQL (let the caller specify the database)
- Update docker-compose default to `dk_data`
- This prevents subtle failures where migrations apply to the wrong database

---

## 2. High Priority Issues (Fix This Sprint)

### 2.1 Production Image Tag Points to Staging

**Severity:** HIGH
**Location:** `k8s/overlays/prod/kustomization.yaml` does not override the image tag

The prod job-trigger deployment uses whatever tag is in the base manifest, which is currently `main-5f46ed1`. However, the build-push workflow updates tags on push to **both** main and staging branches using `sed` on the same base file. This creates a race: a staging push can overwrite the production image tag.

**Recommendation:**
- Use Kustomize `images` transformer in each overlay to pin environment-specific tags:
  ```yaml
  images:
    - name: ghcr.io/data-kinetic/dk-data-fe/job-trigger
      newTag: main-<sha>  # or staging-<sha>
  ```
- Update build-push.yaml to modify overlay-specific files, not the shared base
- Consider a proper promotion flow: staging image tested → promoted to prod

### 2.2 182MB of Raw CSV Data Committed to Git

**Severity:** HIGH
**Location:** `src/dk_data/data/raw/` -- 20 CSV files totaling 182MB

Raw data files (CMS, HRSA, cost reports) are committed to the repository. This bloats clone times, makes CI slower, and is a data management anti-pattern.

**Recommendation:**
- Remove from git tracking: `git rm --cached src/dk_data/data/raw/*`
- Add `src/dk_data/data/raw/` to `.gitignore`
- Store raw data in MinIO (already in the infra namespace) or an S3 bucket
- Use `git filter-branch` or `git-filter-repo` to clean history (optional, coordinate with team)
- Document the data retrieval process in the README

### 2.3 Near-Zero Test Coverage

**Severity:** HIGH
**Current State:** 3 test files (`conftest.py`, `test_security.py`, `test_api.py`) for ~88K lines of Python code. Empty `unit/`, `integration/`, `contract/` directories.

The security and API tests are well-written but only cover PostgREST endpoint access control. Zero tests exist for:
- Fetcher logic (CMS, HRSA, ACC-TVC, molecule clients)
- SQLMesh model correctness
- Data validation/Pydantic models
- FastAPI job-trigger endpoints
- Service layer business logic
- 23 external API clients

**Recommendation (phased):**
1. **Week 1**: Add unit tests for data validators/Pydantic models (high ROI, fast to write)
2. **Week 2**: Add integration tests for fetchers with mocked HTTP responses
3. **Week 3**: Add SQLMesh model tests using `sqlmesh test`
4. **Week 4**: Add job-trigger API tests using FastAPI `TestClient`
5. Target: 30% coverage by end of month, 60% by end of quarter
6. Add `pytest-cov` to CI with a minimum threshold gate

### 2.4 Dependency Pinning with Minimum-Only Constraints

**Severity:** HIGH
**Location:** `pyproject.toml:6-45`

All 45 dependencies use `>=` constraints with no upper bounds and no lock file enforcement in CI. The `uv.lock` exists but the CI workflow uses `pip install -e ".[dev]"`, bypassing it entirely.

**Recommendation:**
- CI should use `uv sync` instead of `pip install` to respect the lock file
- Or adopt `pip-tools` with `requirements.lock` and install from the lock in CI
- Add Dependabot or Renovate for automated dependency updates with PR reviews

---

## 3. Medium Priority Issues (Plan for Next Month)

### 3.1 Observability Gaps

**Current State:**
- OpenTelemetry dependencies installed but the `alloy.infra.svc.cluster.local:4317` OTEL endpoint target is not verified
- ServiceMonitor and PrometheusRule exist but are commented out in kustomization (no Prometheus Operator CRDs)
- Structured logging via structlog is configured but logs go to stdout without aggregation
- No Grafana dashboards defined

**Recommendation:**
- Install Prometheus Operator CRDs (or kube-prometheus-stack) on the k3d cluster
- Uncomment ServiceMonitor/PrometheusRule in kustomization
- Create 3 starter Grafana dashboards: API latency/throughput, CronJob success rate, database connection pool usage
- Verify OTEL traces are reaching Alloy/Tempo

### 3.2 Missing Audit Trail (Issue #17)

No API access logging, no data change tracking. For a healthcare/pharma data platform, this is a compliance concern (21 CFR Part 11, ALCOA+).

**Recommendation:**
- Add PostgREST `pre-request` function for access logging
- Add `audit.api_access_log` table with request metadata
- Add database triggers on critical tables for change tracking
- This is a prerequisite for any regulated-use deployment

### 3.3 CronJob Architecture Fragility

All 5 CronJobs share the same `job-trigger` container image and use `activeDeadlineSeconds: 600`. This means:
- A single broken image blocks ALL data ingestion
- Long-running molecule fetches may exceed the 600s deadline
- No retry logic at the K8s level (no `backoffLimit` seen beyond default)

**Recommendation:**
- Consider separate images or at least separate entrypoints for distinct job types
- Increase `activeDeadlineSeconds` for heavy jobs (mol-fetch-weekly, fetch-cms-all)
- Add explicit `backoffLimit: 3` with exponential backoff
- Add a dead-letter mechanism: log failed jobs to a database table for operator review

### 3.4 Secret Management Documentation (Issue #57)

Doppler is used for secret injection via `DopplerSecret` CRD, but there's no documentation of:
- Which secrets are required per environment
- How to rotate secrets
- What happens if Doppler is unavailable (fallback behavior)

**Recommendation:**
- Create `docs/SECRET_MANAGEMENT.md` documenting all required secrets, their purpose, and rotation procedures
- Add a startup validation check that logs missing or obviously-default secrets

### 3.5 Network Policy Gap for CronJobs

The network policies allow PostgREST and job-trigger ingress, and egress to DNS/Postgres/HTTPS. But CronJob pods inherit the namespace's default-deny policy and may not have the correct labels to match the egress rules.

**Recommendation:**
- Verify CronJob pod labels match the egress NetworkPolicy selectors
- Add explicit NetworkPolicy entries for CronJob pods if needed
- Test with `kubectl exec` from a CronJob pod to verify DNS and HTTPS egress

---

## 4. Issue Tracker Cleanup

### 4.1 Close These 15 Issues (Resolved in Code)

These issues have been fixed in the current codebase based on code review. Keeping them open creates noise and makes actual work harder to prioritize.

| Issue | Title | Evidence of Resolution |
|-------|-------|----------------------|
| #10 | SQLMesh Model Dependencies | SQLMesh models now have explicit `depends_on` |
| #12 | No K8s Resource Limits | All deployments and CronJobs have requests/limits |
| #14 | Incomplete Error Handling | Custom exception hierarchy exists in services |
| #21 | PostgREST Version Mismatch | Pinned to v12.2.3 everywhere |
| #54 | Build and Publish job-trigger Image | `build-push.yaml` workflow exists and runs |
| #55 | Build Container Images for CronJobs | CronJobs use the job-trigger image, built by CI |
| #56 | Fix db-init SQL Syntax Errors | init SQL is valid, db-init job completes |
| #58 | Add PostgREST Health Endpoint | `api.health` view exists in `api_views.sql` |
| #59 | Set Up GitHub Actions CI/CD | `ci.yaml` + `build-push.yaml` are complete |
| #60 | Create Initial API Schema Views | 5+ views in `api` schema confirmed |

Also verify whether #11 (Observability) and #15 (Test Coverage) can be partially closed or converted to tracking epics.

### 4.2 Consolidate Overlapping Issues

Several issues overlap and should be merged:
- **#80 and #81**: Both track missing PostgREST views. #81 supersedes #80 (close #80)
- **#42 and #27**: Both reference OpenAlex integration (molecule vs CI fetcher). Consider a single implementation issue
- **#47 and #30 and #83**: All relate to USPTO/PatentsView. #83 (API key blocker) gates the others

### 4.3 Prioritized Open Issue Backlog

After cleanup, the recommended priority order for genuinely open work:

| Priority | Issue(s) | Rationale |
|----------|----------|-----------|
| **P0** | #13 (DB backups) | Data loss prevention -- nothing else matters if you lose the database |
| **P1** | Fix ghcr-credentials + DNS (no issue) | Unblocks all ingestion pipelines |
| **P1** | #17 (Audit trail) | Compliance requirement for healthcare/pharma |
| **P1** | #81 (Missing API views) | Blocks 6 downstream behavior-labs specs |
| **P2** | #22 (Production readiness meta) | Umbrella for remaining hardening |
| **P2** | #57 (Doppler documentation) | Operational knowledge currently in one person's head |
| **P2** | #20 (Dependency management) | Prevents "works on my machine" drift |
| **P3** | #41-#51 (Data source enablement) | New capabilities, not fixing broken things |
| **P3** | #26-#35 (CI fetchers) | New capabilities |
| **P4** | #52 (Frontend integration) | Depends on stable API surface first |

---

## 5. Architecture Observations

### 5.1 Strengths

- **Medallion architecture** (raw → bronze → silver → gold → api) is well-designed and appropriate for the use case
- **PostgREST** as the API layer is a pragmatic choice -- minimal code, automatic OpenAPI, role-based security via PostgreSQL roles
- **Kustomize overlays** with environment-specific patches are clean and maintainable
- **SQLMesh** for transformation DAG management is modern and testable
- **Security model** with JWT + PostgreSQL roles + restricted `web_anon` is sound
- **Network policies** with default-deny are production-appropriate

### 5.2 Concerns

- **Dual API surface**: FastAPI job-trigger (`/health`, `/jobs`) AND PostgREST (`/health`, `/targets`, `/scoring`). These serve different purposes but could confuse operators and create surface area to secure. Consider documenting which API serves which consumer.
- **23 external API clients** with no circuit breaker or rate-limit coordination. If multiple fetchers run concurrently, they could overwhelm external APIs or hit rate limits unpredictably.
- **Single shared database** for all environments via namespace isolation. If staging runs a bad migration, it affects the shared PostgreSQL instance. Consider separate logical databases or at minimum separate schemas per environment.
- **No data validation between pipeline stages**. Data flows from fetcher → raw → SQLMesh with no intermediate quality gates. A corrupt source file could propagate bad data to gold views.

### 5.3 Scaling Considerations

The current setup (single k3d node, 1 PostgreSQL instance) is fine for development. For production scale:
- PostgreSQL should move to CloudNativePG with streaming replication (at least 1 replica)
- PostgREST connection pool (currently 10 staging, 20 prod) may need PgBouncer in front for connection multiplexing
- CronJobs should have resource limits tuned based on actual usage (currently 64Mi-256Mi for job-trigger, which may be too low for molecule transformation)

---

## 6. Quick Wins (< 1 Day Each)

| # | Action | Impact |
|---|--------|--------|
| 1 | Create `ghcr-credentials` secret in both namespaces | Unblocks all ingestion |
| 2 | Fix k3d DNS resolution | Enables image pulls |
| 3 | Close 15 resolved GitHub issues | Reduces noise, clarifies backlog |
| 4 | Replace hardcoded password in `init_database.sql` | Security hygiene |
| 5 | Add `src/dk_data/data/raw/` to `.gitignore` | Stops repo bloat growth |
| 6 | Standardize database name to `dk_data` in docker-compose | Eliminates config drift |
| 7 | Add `pytest-cov --cov-fail-under=10` to CI | Establishes coverage floor |
| 8 | Pin image tags per overlay instead of shared base | Prevents staging→prod tag bleed |

---

## 7. Recommended 30-Day Roadmap

### Week 1: Unblock Ingestion
- [ ] Fix `ghcr-credentials` and DNS issues
- [ ] Verify all 5 CronJobs run successfully
- [ ] Close resolved GitHub issues
- [ ] Fix hardcoded credential in init SQL

### Week 2: Data Safety
- [ ] Implement pg_dump backup CronJob to MinIO
- [ ] Add backup verification job (weekly restore test)
- [ ] Remove raw CSV data from git
- [ ] Standardize database name

### Week 3: Testing & CI
- [ ] Add Pydantic model unit tests (target: 20 tests)
- [ ] Add fetcher integration tests with mocked HTTP (target: 15 tests)
- [ ] Add coverage threshold gate to CI
- [ ] Switch CI to use `uv sync` for deterministic installs

### Week 4: Observability & Compliance
- [ ] Install Prometheus Operator CRDs, enable ServiceMonitor
- [ ] Create initial Grafana dashboards
- [ ] Begin audit trail implementation (PostgREST pre-request logging)
- [ ] Document secret management procedures

---

*Generated by Claude Opus 4.6 based on comprehensive review of the repository, all 50 open GitHub issues, and live Kubernetes cluster state.*

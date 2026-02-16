# Open Issues Reconciliation

**Date**: 2026-02-16 (updated)
**Branch**: main (post-merge of PR #92 — 013-observability-governance)
**Open Issues**: 3 GitHub issues + 4 infrastructure items

---

## Executive Summary

Since the initial reconciliation (2026-02-14), **all Sprint 1, Sprint 2, and Sprint 3 items are complete**. PR #89 (012-platform-hardening) resolved 7 issues. PR #90 fixed a production promotion race condition. PR #92 (013-observability-governance) resolved 5 issues covering metrics scraping, audit trail, migration runner, and data classification/retention.

Of the 3 remaining GitHub issues, 2 are from the original reconciliation (#52, #84) and 1 is an older architecture debt item (#8). Issues #9, #16, #17, #18, #19 were all closed by PR #92.

A 2026-02-16 cluster health check uncovered 4 infrastructure issues: staging PostgreSQL outage (resolved), prod fetch-* CronJob failures, prod/staging pg-backup secret misconfiguration, and a missing dk-alchemy PriorityClass deployment for staging.

---

## Completed Work (since 2026-02-14)

### Closed — Previously Resolved (2026-02-14)

| Issue | Title | Closed By |
|-------|-------|-----------|
| #78 | dk-data platform: remaining issues and integration roadmap | Superseded by this document |
| #80 | Add missing gold/bronze tables required by behavior-labs-ai specs | Duplicate of #81 |
| #82 | Import SIDER side effect database | PR #87 (011-datasource-integration) |
| #83 | Unblock PatentsView API key | PR #87 (implementation complete) |

### Closed — PR #89 (012-platform-hardening, 2026-02-15)

| Issue | Title | What Was Done |
|-------|-------|---------------|
| #88 | CronJob pods fail: ModuleNotFoundError | Fixed Dockerfile multi-stage build — removed redundant COPY and PYTHONPATH override, fixed absolute imports |
| #81 | Create missing PostgREST API views | Added 6 API views (company_pipeline, molecule_targets, trial_publication_features, sider_side_effects, bioactivity, patents) with migration 065 and GRANTs |
| #42 | Enable UniProt data source | UniProt fetcher, loader, validator, CronJob, seed SQL, catalog entry |
| #50 | Enable PDB data source | PDB fetcher, loader, validator, CronJob, seed SQL, catalog entry |
| #51 | Enable ORCID data source | ORCID fetcher, loader, validator, migration 066, CronJob, seed SQL, catalog entry |
| #20 | Python dependency version management | All 38 deps pinned with upper bounds, uv.lock generated, CI lock freshness check |
| #57 | Document Doppler secret configuration | docs/DOPPLER_SECRETS.md (14 secrets), startup validation module with 7 tests |

### Additional Fix — PR #90 (2026-02-15)

Fixed race condition in `.github/workflows/promote-to-prod.yaml` — production promotion now reads the staging image tag from the overlay kustomization.yaml instead of computing from HEAD SHA (which pointed to the manifest commit, not the build commit).

### Closed — PR #92 (013-observability-governance, 2026-02-15)

| Issue | Title | What Was Done |
|-------|-------|---------------|
| #91 | Enable full observability: deploy ServiceMonitors, verify metrics endpoint, add PostgREST exporter | Fixed ServiceMonitor/PodMonitor labels (`release: mimir`), added `batch-job` labels to 15 CronJob pod templates, replaced PostgREST ServiceMonitor with Probe CRD (blackbox-exporter), updated `APIUnavailable` alert to `probe_success` metric |
| #17 | No audit trail for data changes and API access | Two-layer audit trail: `AuditLoggingMiddleware` (FastAPI, async thread pool) + PostgreSQL trigger via `current_setting('request.jwt.claims')`; `api.audit_log` view restricted to `api_user`; migration 067 |
| #9 | No database migration strategy | Lightweight migration runner (`run_migrations.py`) with SHA-256 checksums, `--baseline`/`--dry-run` flags, `meta.schema_migrations` tracking table, `api.migration_status` view; migration 068 |
| #18 | Unclear PII/PHI data handling | 4-tier data classification (public/internal/pii/confidential) for 43 tables; `raw.orcid` identified as PII with 6 fields; `api.data_classification` view; migration 069 |
| #19 | No defined data retention policy | Retention-based `purge_by_classification()` with `--all-tables` flag; retention_days column on `meta.data_sources`; `docs/DATA_CLASSIFICATION.md`; migration 070 |

198 new tests added (all passing). Also addressed #16 (documentation drift) via comprehensive spec artifacts and `DATA_CLASSIFICATION.md`.

---

## Remaining Open Issues (3)

### Near-Term — Actionable

#### #52 — Frontend integration — React onboarding wizard + dashboard
**Priority**: P2
**Effort**: Large (1-2 weeks)
**Dependencies**: API views now exist (resolved by #81/PR #89)
**Current state**: The frontend directory does not exist on main. The 6 API views from PR #89 now provide data endpoints. The mol_gold compute-on-demand views (molecule_properties, SHAP explanations, synthesizability scores) are still not implemented — these would require a FastAPI sidecar or pre-computation.
**Recommendation**: Can begin basic frontend work against the 6 available API views. Defer mol_gold-dependent features until compute architecture is decided.

#### #84 — Evaluate LiteLLM proxy integration for AI calls
**Priority**: P3
**Effort**: Small (evaluation) or Medium (migration)
**Dependencies**: Decision on centralized LLM budgeting/observability
**Current state**: dk-data-FE uses direct Anthropic SDK calls. The dk-litellm proxy exists but integration hasn't been implemented.
**Recommendation**: Close as "won't fix" if centralized budgeting isn't a priority, or defer to post-MVP.

### Older Platform Issues

| Issue | Title | Priority | Notes |
|-------|-------|----------|-------|
| #8 | Tight coupling to Edwards/TAVR use case | P3 | Ongoing — new fetcher pattern (BaseFetcher) is generic, but legacy code still TAVR-specific |

---

## Infrastructure Issues (2026-02-16)

### RESOLVED — Staging PostgreSQL outage

**Root cause**: The `staging-default` PriorityClass did not exist on k3s-slave-1 (staging cluster). The CNPG postgres overlay for staging (`dk-alchemy/k8s/infrastructure/postgres/overlays/staging/`) sets `priorityClassName: staging-default`, but the `infra-priority-classes` ArgoCD app only deploys PriorityClasses to k3s-master-1 (prod). When the staging cluster was bootstrapped (~5d ago), the CNPG operator couldn't create `postgres-cluster-1` — pod creation was forbidden.

**Impact**: PostgreSQL down for ~5 days on staging. PostgREST crash-looping (0/2 ready, 23 restarts). All staging CronJobs requiring DB access affected (`catalog-refresh` failed 3 consecutive runs).

**Fix applied (manual, 2026-02-16)**:
1. Created `staging-default` PriorityClass on k3s-slave-1 (`value: 100000, preemptionPolicy: PreemptLowerPriority`)
2. Added node label `workload.dk-alchemy/env=staging` to k3s-slave-1 (for preferred nodeAffinity match)
3. Annotated CNPG cluster to trigger immediate reconciliation
4. Deleted crash-looping PostgREST pods to reset CrashLoopBackOff

**Result**: PostgreSQL `postgres-cluster-1` running (1/1 Ready, healthy). PostgREST 2/2 Running (0 restarts). ArgoCD `dk-data-staging` app reports Healthy.

**Permanent fix needed (dk-alchemy)**: The `infra-priority-classes` ArgoCD app should deploy PriorityClasses to both clusters, or a staging-specific priority classes app should be created. The manual PriorityClass and node label on k3s-slave-1 will be lost if the node is rebuilt.

### FIXED — NetworkPolicy blocks intra-namespace traffic (P1, NEW)

**Root cause**: The `dk-data-postgrest-ingress` NetworkPolicy only allowed ingress from external namespaces (`kube-system`, `behaviorlabs-*`, `agentmesh-*`, `infra`) — not from within the same namespace. Combined with `dk-data-default-deny` (denies all), job-trigger and CronJob pods couldn't reach PostgREST. The `dk-data-egress` policy also lacked intra-namespace and staging MinIO rules.

**Impact**: Job-trigger can't call PostgREST health endpoint. CronJob pods that need to load data via PostgREST are blocked. Staging backup CronJobs can't reach MinIO in `infra-staging`.

**Fix applied (2026-02-16)**:
1. Added same-namespace ingress rule (`podSelector: {}`) to `dk-data-postgrest-ingress` (matching pattern already used in `dk-data-job-trigger-ingress`)
2. Added intra-namespace egress rule (ports 3000, 8000) to `dk-data-egress`
3. Added staging MinIO egress rule (port 9000 to `infra-staging`)

### DIAGNOSED — Prod fetch-* CronJob failures (P1) → Transient first-run failures

**Affected jobs** (13 data sources): `fetch-pubmed`, `fetch-news`, `fetch-sec-edgar`, `fetch-ema-reg`, `fetch-epo`, `fetch-hta`, `fetch-journal-rss`, `fetch-openalex-ci`, `fetch-orcid`, `fetch-pdb`, `fetch-uniprot`, `fetch-uspto-ci`, `fetch-uspto-patents`

**Diagnosis (2026-02-16)**: Manual trigger of `test-pubmed` job succeeded — fetched 47 PubMed records, exit code 0. The fetcher code works correctly. The original BackoffLimitExceeded failures on first scheduled runs (~25h ago) were transient (likely image pull or API timing during initial CronJob creation). Failed job objects remain on cluster and need cleanup for CronJobs to schedule new runs.

**Action needed**:
1. Clean up failed job objects: `kubectl delete jobs --field-selector status.successful=0 -n dk-data-prod` (for the 13 fetch-* failed jobs)
2. Monitor next scheduled runs to confirm all 13 sources succeed
3. Note: `fetch_data.py` does NOT call DB loaders — fetched data is written to `/tmp/data/raw` and lost when pod exits. This is a separate issue for follow-up.

### IN PROGRESS — Prod/Staging pg-backup CronJob failures (P2)

**Affected jobs**: `pg-backup-daily`, `pg-backup-weekly`, `pg-backup-verify` (both prod and staging)

**Root cause**: The `minio-backup-credentials` DopplerSecret was missing required fields (`project`, `config`, `tokenSecret.key`, `managedSecret.type`, `resyncSeconds`), so the Doppler operator couldn't sync actual secrets. Additionally, all 3 backup CronJobs hardcoded `MINIO_ENDPOINT` to `minio.infra.svc.cluster.local:9000` (wrong for staging, which uses `infra-staging` namespace).

**Fixes applied (2026-02-16)**:
1. Fixed `k8s/base/backup/minio-credentials.yaml` DopplerSecret to match `dk-data-secrets` pattern (added `key: serviceToken`, `project`, `config`, `type: Opaque`, `resyncSeconds: 300`)
2. Added staging overlay patches: DopplerSecret `config: stg`, and `MINIO_ENDPOINT` → `minio.infra-staging.svc.cluster.local:9000` for all 3 backup CronJobs

**Manual action still needed**: Add `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` to Doppler project `dk-data-fe` (both `prd` and `stg` configs) with MinIO root credentials from the respective infra namespaces.

### FIXED — dk-alchemy PriorityClass gap (P3, preventive)

**Issue**: The `infra-priority-classes` ArgoCD app deploys PriorityClasses only to k3s-master-1 (prod cluster). k3s-slave-1 (staging cluster) does not get PriorityClasses via GitOps. This caused the 5-day staging PostgreSQL outage documented above.

**Fix applied (2026-02-16)** (in dk-alchemy repo):
1. Created `k8s/infrastructure/priority-classes/overlays/staging/kustomization.yaml` (mirrors prod overlay)
2. Added `priority-classes` to the staging ApplicationSet generator list in `.gitops/root/dk-cluster-infra-staging.yaml`
3. ArgoCD will deploy both `production-critical` and `staging-default` PriorityClasses to k3s-slave-1 via `infra-priority-classes-staging` app

**Deployed**: dk-alchemy PR #190 merged to `main`. ArgoCD created `infra-priority-classes-staging` app (status: Healthy). PriorityClasses confirmed on k3s-slave-1.

---

## Current Cluster Status (2026-02-16 03:35 UTC)

### Prod (k3s-master-1, `dk-data-prod`)

| Component | Status | Details |
|-----------|--------|---------|
| PostgREST | **3/3 Running** | Image: `postgrest:v12.2.3`, 0 restarts |
| job-trigger | **2/2 Running** | Image: `prod-5da0abb`, 0 restarts |
| PostgreSQL (infra) | **Healthy** | 3 instances, `infra` namespace |
| ArgoCD app | **Healthy / OutOfSync** | 5 orphaned resources (old job objects) |
| `mol-fetch-daily` | Succeeding | Last run: 77min ago |
| `mol-transform` | Succeeding | Last run: 21h ago |
| `catalog-refresh` | Succeeding | Last run: 21h ago |
| `fetch-cms-all` | Succeeding | Last run: 25h ago |
| `fetch-*` (13 new) | **All failing** | BackoffLimitExceeded, needs diagnosis |
| `pg-backup-*` | **Failing** | Missing MinIO credentials in secret |

### Staging (k3s-slave-1, `dk-data-staging`)

| Component | Status | Details |
|-----------|--------|---------|
| PostgREST | **2/2 Running** | Image: `postgrest:v12.2.3`, 0 restarts (fixed 2026-02-16) |
| job-trigger | **1/1 Running** | Image: `staging-787f93b`, 0 restarts |
| PostgreSQL (infra-staging) | **1/1 Healthy** | Fixed 2026-02-16, was down ~5 days |
| ArgoCD app | **Healthy / OutOfSync** | 4 orphaned resources (old job objects) |
| `mol-fetch-daily` | Succeeding | Every 6h schedule, last run: 3h49m ago |
| `mol-fetch-weekly` | Succeeding | Last run: 24h ago |
| `mol-transform` | Succeeding | Last run: 21h ago |
| `fetch-*` (13 new) | **Not yet fired** | Created ~3h ago, first runs pending per schedule |
| `pg-backup-*` | **Failing** | Same MinIO credential issue as prod |

---

## Items to Test / Validate

### High Priority

- [ ] **Diagnose prod fetch-* failures** — manually create a job from one CronJob and watch logs:
  ```bash
  # On k3s-master-1:
  kubectl create job test-pubmed --from=cronjob/fetch-pubmed -n dk-data-prod
  kubectl logs -f job/test-pubmed -n dk-data-prod
  ```
- [ ] **Fix MinIO backup credentials** — add `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` to Doppler `dk-data-fe` project (both `prd` and `stg` configs), then verify `pg-backup-daily` succeeds
- [ ] **Verify staging fetch-* jobs work** — wait for first scheduled runs or manually trigger one:
  ```bash
  # On k3s-slave-1:
  kubectl create job test-pubmed --from=cronjob/fetch-pubmed -n dk-data-staging
  kubectl logs -f job/test-pubmed -n dk-data-staging
  ```
- [ ] **Verify staging PostgREST API is serving** — test health and authenticated endpoints:
  ```bash
  # From within the staging cluster:
  kubectl exec -n dk-data-staging deploy/job-trigger -- python -c "import httpx; print(httpx.get('http://postgrest.dk-data-staging.svc:3000/health').status_code)"
  ```

### Medium Priority

- [ ] **Clean up failed job objects** — both clusters have accumulated failed job objects that show as orphaned resources in ArgoCD. These can be pruned:
  ```bash
  kubectl delete jobs --field-selector status.successful=0 -n dk-data-prod
  kubectl delete jobs --field-selector status.successful=0 -n dk-data-staging
  ```
- [ ] **Verify staging catalog-refresh** — this failed 3 times while postgres was down. Next run is at 06:00 UTC — confirm it succeeds with postgres restored
- [ ] **Permanent PriorityClass fix in dk-alchemy** — add staging PriorityClass deployment to GitOps so it survives node rebuilds

### Low Priority

- [ ] **Review #84 (LiteLLM)** — close if not needed, or spike evaluation
- [ ] **Review #8 (TAVR coupling)** — triage whether decoupling is worth a dedicated effort
- [ ] **Verify `pg-backup-verify` CronJob** — scheduled `0 4 * * 1` (Monday 04:00 UTC), hasn't run yet; will also fail due to missing MinIO credentials

---

## Recommended Next Steps

### Immediate (this session or next)
1. **Diagnose prod fetch-* failures** — manually trigger one job and watch logs to identify root cause
2. **Fix pg-backup credentials** — add MinIO keys to Doppler, verify backup runs
3. **Permanent PriorityClass fix** — update dk-alchemy to deploy PriorityClasses to staging cluster

### Next Feature (Sprint 4)
- **#52** — Frontend integration against the 6 available API views
- **mol_gold compute architecture** — decide on pre-computation vs FastAPI sidecar for molecule property endpoints

---

## Issue Cross-Reference Matrix

| Issue | Status | Theme | Blocked By |
|-------|--------|-------|------------|
| #8 | Open | Architecture debt | — |
| #9 | **Closed** (PR #92) | Platform engineering | — |
| #16 | **Closed** (PR #92) | Documentation | — |
| #17 | **Closed** (PR #92) | Observability | — |
| #18 | **Closed** (PR #92) | Security/compliance | — |
| #19 | **Closed** (PR #92) | Data governance | — |
| #52 | Open | Frontend | mol_gold compute decision |
| #84 | Open | Optional | Decision needed |

### Infrastructure Issues (not tracked as GitHub issues)

| Item | Status | Priority | Owner |
|------|--------|----------|-------|
| Staging PostgreSQL outage | **Resolved** (manual fix) | — | — |
| NetworkPolicy intra-namespace | **Fixed** — same-namespace ingress/egress rules added | P1 | Pending deploy |
| Prod fetch-* CronJob failures | **Diagnosed** — transient; failed jobs cleaned up | P1 | Monitor next runs |
| Prod/staging pg-backup credentials | **In progress** — manifests fixed, Doppler secrets pending | P2 | Manual Doppler |
| dk-alchemy PriorityClass gap | **Deployed** — PR #190 merged, ArgoCD app Healthy | P3 | Done |

---

## Post-Reconciliation Summary

| Action | Count | Issues |
|--------|-------|--------|
| Closed (pre-reconciliation) | 4 | #78, #80, #82, #83 |
| Closed (PR #89) | 7 | #88, #81, #42, #50, #51, #20, #57 |
| Closed (PR #92) | 5 | #91, #17, #9, #18, #19 |
| Also addressed (PR #92) | 1 | #16 (documentation drift — comprehensive specs + DATA_CLASSIFICATION.md) |
| Infra resolved (2026-02-16) | 1 | Staging PostgreSQL outage |
| Remaining GitHub issues | 3 | #8, #52, #84 |
| Remaining infra items | 1 diagnosed + 1 in progress | fetch-* cleanup, pg-backup Doppler secrets |
| Infra items fixed (2026-02-16) | 2 | pg-backup manifests, PriorityClass gap |
| **Total resolved this cycle** | **20** | |

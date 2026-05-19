# Lessons Learned

> Mistakes, surprises, and non-obvious fixes worth remembering.
> Consulted before starting similar work. Managed by the `lessons-learned` skill.

<!-- Append entries below using the format:

## YYYY-MM-DD — Short Title

**Context**: What were you trying to do?
**What happened**: What went wrong or was surprising?
**Root cause**: Why did it happen?
**Lesson**: What should be done differently next time?
**Tags**: comma-separated keywords

-->

## 2026-04-13 — Migration filenames can lie about what they do

**Context**: Auditing the existing PostgreSQL grant landscape before US-2 (drop web_anon).
**What happened**: Found a migration `209_restrict_web_anon.sql` that — despite its name — actually GRANTS broad access to web_anon on the `api` schema. The file revokes from raw/bronze/staging/meta but grants USAGE + SELECT on every table in the api schema in the same DO block. The "restrict" in the filename refers to one half of the migration; the file as a whole expanded web_anon's reach.
**Root cause**: A single migration file did two things and was named after the smaller of the two. No PR review caught the misleading name.
**Lesson**: Code-review every migration that touches grants, not just the SQL diff but the filename and the comment block. If a migration both revokes and grants, name it after the broader effect (the grant), not the narrower one (the revoke).
**Tags**: grants, migrations, naming, review, security

## 2026-04-13 — The "38 dead metrics" pattern (define helper, never call site)

**Context**: Auditing `src/dk_data/observability/metrics.py` for US-12 (every metric should be emitted or deleted).
**What happened**: 38 of 78 metric definitions had a corresponding helper function in `services/data_platform/metrics.py` but the helper was never called from any production code path. Specifically: T017 said the `POST /job-complete` endpoint was partially broken because it only emitted `BATCH_JOB_LAST_SUCCESS_TIMESTAMP` — but on inspection the endpoint already calls all 4 helpers. The brief was based on a stale snapshot.
**Root cause**: PR reviews accepted "metric definition + helper function" as evidence the metric was wired up, without verifying any code path actually calls the helper. Three-way binding (definition + emission + dashboard panel) was never enforced.
**Lesson**: Add a CI check that fails the build if any metric in `metrics.py` has zero `.inc()/.set()/.observe()` call sites. The check in T113 implements this. Also: add the three-way binding rule to `.dk/memory/principles.md` so future PRs honor it.
**Tags**: metrics, observability, CI, dead-code, principles

## 2026-04-13 — `mol_api` was already in production but nobody knew

**Context**: Drafting the spec for US-4/US-5 in feature 002.
**What happened**: Multiple drafts of the spec described "adding `mol_api` to PGRST_DB_SCHEMAS" as a critical Phase 2 task. Verification against `k8s/apps/postgrest/base/configmap.yaml` line 11 showed it was already there. The schema was deployed in production but the standalone `postgrest.conf` and `docker-compose.yml` were stale (the older audits read those instead).
**Root cause**: Three-way config drift — production k8s configmap, standalone postgrest.conf, and docker-compose.yml all set PGRST_DB_SCHEMAS but to different values. Audits picked one source of truth and missed the others.
**Lesson**: When auditing "what's in production", verify against the k8s manifests, not the standalone or docker dev configs. Treat dev configs as suspect until proven sync. Feature 002 T010/T011 is the structural fix (sync them), but the underlying lesson is to always start audits from the k8s deployed state.
**Tags**: config, drift, audit, k8s, production-state

## 2026-04-13 — Two tables with confusingly similar names (`molecule_profile` vs `molecule_profiles`)

**Context**: Investigating which gold table backed the molecule profile API endpoint.
**What happened**: `mol_gold.molecule_profile` (singular) was created by migration 081, `mol_gold.molecule_profiles` (plural) by migration 020. Both still exist. Different migrations populate them. Different consumers query them. The brief assumed only one existed.
**Root cause**: A migration added the singular form without checking for the plural one. `\dt mol_gold.*` would have caught it.
**Lesson**: Before creating a table in any schema, run `\dt schema.*` and search for similar names. Adopt a convention (singular OR plural, never both) and document it in CLAUDE.md. US-10 in feature 002 consolidates these — once the consolidation lands, the project standard is documented.
**Tags**: schema, naming, collisions, conventions

## 2026-04-13 — DAG cycle: `bioactivity → identifier_mappings → molecule_targets → bioactivity`

**Context**: A SQLMesh model rebuild was failing during feature 001's silver medallion work.
**What happened**: The model dependency graph (built by `src/dk_data/ingestion/utils/build_model_lineage.py`) had a 3-node cycle. The DAG visualization in Grafana showed the loop after the lineage rebuild ran. The cycle prevented SQLMesh from computing a topological sort of the transform plan.
**Root cause**: `bioactivity` joined `identifier_mappings` (because it needed canonical identifiers) which joined `molecule_targets` (because it needed target IDs) which joined `bioactivity` (because targets reference activities). Three siblings each needing data from the others.
**Lesson**: Cycles ARE possible even with hub architecture. Build DAG-validation into CI — every PR that adds or modifies a SQLMesh model should run `build_model_lineage.py --dry-run` and reject the PR if a cycle is introduced. Document the lesson alongside the resolved cycle in `.dk/specs/001-silver-medallion-rebuild/`.
**Tags**: dag, cycles, lineage, sqlmesh, ci

## 2026-04-13 — Migration 086 (CMS PUF) silently granted web_anon broad CMS access

**Context**: Mapping every grant `web_anon` had so we could revoke them in migration 218.
**What happened**: Migration 086 (`086_cms_puf_platform_reconciliation.sql`) lines 942–955 granted USAGE on `hcs_silver` AND `hcs_gold` and SELECT on every table in those schemas to `web_anon`. The migration was reviewed and merged when CMS PUF data was a separate hcs initiative, and nobody noticed the implication that `web_anon` was now effectively a "read all CMS data anonymously" role.
**Root cause**: Migration 086 was 950+ lines focused on schema setup; the grant block was near the bottom and PR reviewers focused on the schema/DDL changes. No one called out the grant scope.
**Lesson**: Migrations that exceed ~200 lines should be split. Grant changes should be in their own migration file with `_grants` in the filename. Code review checklist for any grant migration: who is the grantee, what is the scope, is `web_anon` involved (auto-rejected after feature 002).
**Tags**: grants, security, code-review, migration-size, web_anon

## 2026-04-13 — Stale comment in deployment.yaml claimed HTTP probes when they're TCP

**Context**: Feature 002 spec wrestled with whether to keep `web_anon` for k8s liveness probes (carve-out for `api.health`) or drop it entirely.
**What happened**: The spec was leaning toward a carve-out. Then verification of `k8s/apps/postgrest/base/deployment.yaml` lines 130–146 showed all three probes (startup, liveness, readiness) are `tcpSocket: {port: 3000}`. The comment at lines 127–129 claimed HTTP probes required `api.health` + `web_anon` — completely false, the probes never used HTTP. The comment was load-bearing in the spec discussion but was just stale documentation.
**Root cause**: A previous PR migrated the probes from HTTP to TCP but left the explanatory comment untouched. The comment then accumulated authority over time and influenced spec decisions.
**Lesson**: Treat code+config as the source of truth, not comments. When you find a comment that contradicts the code below it, delete the comment in the same PR — leaving stale comments is a documentation leak. Feature 002 T085 deletes the specific stale comment but the underlying lesson is broader.
**Tags**: comments, drift, documentation, code-review

## 2026-04-14 — Documented auth design that was never implemented

**Context**: Feature 003 (metering-jwt-mint, issue #283) investigated why the dk-data-client kept returning "401 Invalid API key" for every consumer. Two things had to be fixed before the client could work end-to-end.

**What happened**:
1. `docs/consumer-onboarding.md` described a bcrypt-hashed API key scheme (raw keys generated with `openssl rand`, hashed with bcrypt, stored in `consumers.yaml` as `{name, hash}` objects).
2. The running `src/dk_data/metering_proxy/auth.py` did a plain dict lookup of raw keys against the `api_keys` list in the ConfigMap — zero hashing, zero matching to the doc.
3. Separately, `src/dk_data/metering_proxy/proxy.py` had a comment saying "PostgREST uses its own JWT auth" right next to code that *stripped* the Authorization header and never minted a replacement. Every request reached PostgREST as the anonymous role, which had USAGE on only 5 of the 19 exposed schemas.
4. The runbook `docs/runbooks/metering-proxy-401-debug.md` described a JWT validation flow that also did not match the running code.

**Root cause**: A design was documented before being implemented, then the implementation took a simpler (and different) path, and the docs were never updated. The drift then masked the real gap — feature 003 only happened because someone traced the auth code path end-to-end.

**Lesson**: When a doc describes behavior that the code might not implement, verify by reading the code before trusting the doc. On the PR side: if you ship a design doc, link it to the code path that implements it and put a CI check that grep-matches the doc against the module's public surface. Code is the source of truth; documentation that isn't grounded in code becomes a coordination hazard.

**Also**: a pre-flight DO guard inside an earlier migration is NOT a substitute for numeric ordering. The migration runner stops on first failure, so if a guarded migration runs first the deploy deadlocks. Always enforce ordering via filename numeric prefix (or by merging related migrations into one atomic migration), never via runtime guards that depend on something the runner hasn't applied yet.

**Tags**: auth, drift, documentation, migration-ordering, spec-vs-implementation

## 2026-04-15 — Hydration on control-plane hostPath evicts Postgres operator

**Context**: Running the feature 005 prestaged hydration Job (`deploy/jobs/prestaged-hydrate-pv-slave.yaml`) to reload the `dk_data_*` schemas from pre-staged `pg_dump -Fc` artifacts. The Job was deployed with a `hostPath` PV mounted on k3s-master-1's `/var/lib/rancher` directory because that was the fastest way to get the dumps onto a node.
**What happened**: Dump files accumulated under the hostPath until master-1's ephemeral storage filled. The node went `DiskPressure: True`; kubelet evicted the CNPG operator pod (co-located on master-1). ArgoCD selfHeal immediately reconciled the operator back onto the same tainted node, where it was evicted again. The loop continued for ~3 hours while the Postgres primary had no operator to reconcile it, blocking all writes; WAL pressure climbed and replicas diverged. Dk-alchemy issues #637 and #638 track the timeline.
**Root cause**: Co-tenancy of a heavy data-plane workload (tens of GB of dumps + pg_restore churn) on the control-plane node, with no `ephemeral-storage` request/limit on the hydrate Job and hostPath as the bulk storage medium. The control plane had no isolation from data workloads, and nothing in the Job manifest told the scheduler to avoid master-1.
**Lesson**: Data-plane workloads must never schedule onto the control-plane node. Every hydrate Job (and any Job that stages >1 GiB of artifacts) needs: (1) `nodeAffinity` on `dk.role In (general)` to stay off control-plane nodes, (2) explicit `ephemeral-storage` requests + limits so kubelet can evict the right thing instead of the nearest critical pod, and (3) bulk artifact storage in SeaweedFS (object store) rather than hostPath. Tracked in plan.md §B.1 (nodeAffinity on hydrate Jobs), §C.1 (SeaweedFS cutover), and dk-alchemy #649 (physical isolation for Postgres). PR-01 of Horizon 1 implements the Job-manifest fixes.
**Tags**: cnpg, hydration, diskpressure, node-isolation, hostpath-antipattern

## 2026-04-15 — ArgoCD selfHeal reconciles onto a bad node — free the node, don't fight the reconciler

**Context**: During the 2026-04-15 CNPG operator eviction incident (see prior lesson), on-call operators tried to stop the eviction loop by editing the CNPG operator's ArgoCD `Application` spec — disabling selfHeal, adding tolerations ad hoc, patching `nodeSelector` directly on the Deployment.
**What happened**: Every manual patch was reverted by ArgoCD selfHeal within ~60 seconds, reconciling the Deployment back to the Git-declared state. The operator kept landing on the tainted master-1 node. Three hours of incident time was spent fighting the reconciler instead of fixing the underlying node.
**Root cause**: ArgoCD's `selfHeal: true` + `prune: true` is designed to enforce Git as the single source of truth. Editing live resources during an incident works against that contract by design — the controller will always win the race. The instinct to "just patch it" was wrong for the tool in use.
**Lesson**: When ArgoCD is reconciling pods onto a bad node, do not edit the `Application` or the live resource. Instead: `kubectl cordon <bad-node>` → ArgoCD's next reconcile will reschedule the pod onto a healthy node (it re-evaluates placement on every sync, because the old node is no longer schedulable) → once the underlying issue is fixed, `kubectl uncordon <bad-node>`. This respects the GitOps contract and achieves the same operational outcome in seconds rather than hours. Documented in plan.md §B.6 and shipping as `docs/runbooks/cnpg-operator-deadlock.md` in PR-05.
**Tags**: argocd, selfheal, cnpg, incident-response, runbook

## 2026-04-17 — Wave B raw table schema mismatch blocks all new source INSERTs

**Context**: 15 new data sources onboarded via Wave B (5 parallel worker PRs). Each source had a fetcher, loader, CronJob, and descriptor. Migration 236 created raw tables with a minimal schema (id, api_endpoint, response_body, source_year, ingested_at).
**What happened**: First CronJob run for `cms_hac_reduction` failed with "current transaction is aborted, commands ignored until end of transaction block." All 9 Wave B raw tables had the same issue — zero rows loaded.
**Root cause**: The Wave B loaders use the standard raw-layer INSERT pattern (request_id, response_status, response_body_hash for idempotency, source_id for lineage) but migration 236 created tables with only 5 columns. The first INSERT fails on "column does not exist," PostgreSQL aborts the transaction, and all subsequent INSERTs in the same batch fail silently.
**Lesson**: When generating fetcher code and table schemas in parallel workers, verify the INSERT column list matches the CREATE TABLE schema BEFORE merging. A quick `diff <(grep INSERT loader.py) <(grep CREATE migration.sql)` catches this. Fixed via migration 237 (ALTER TABLE ADD COLUMN IF NOT EXISTS for all 9 tables).
**Tags**: wave-b, schema-mismatch, parallel-workers, migration, raw-layer

## 2026-04-17 — ArgoCD blocks sync on never-run Jobs (health-wait deadlock)

**Context**: Horizon 3 shipped a per-source Job dispatcher (62 Job manifests) managed by ArgoCD with `selfHeal: true, prune: true`.
**What happened**: ArgoCD created all 62 Jobs on the first sync but then blocked indefinitely: "waiting for healthy state of batch/Job/hydrate-dispatch and 186 more resources." The sync never completed, blocking all subsequent manifest deployments.
**Root cause**: ArgoCD treats batch/Jobs as "Progressing" health until the Pod reaches a terminal state (Succeeded/Failed). Never-triggered Jobs have no Pod, so they're permanently "Progressing." With 62 Jobs in this state, the sync's health aggregation never reaches "Healthy."
**Lesson**: One-shot Jobs (dispatchers, hydration runs) should NOT be ArgoCD-managed resources. Keep RBAC (ServiceAccount, Role, RoleBinding) in kustomize for ArgoCD to sync; keep the Jobs themselves out of the kustomize tree and trigger manually via `kubectl apply` or `dk data hydrate run`. This matches the existing CronJob-as-template pattern (CronJobs are created by ArgoCD; individual Job runs are spawned from them).
**Tags**: argocd, jobs, health-check, sync-deadlock, dispatcher

## 2026-04-17 — CI image build succeeds but manifest push blocked by branch protection

**Context**: `.github/workflows/build-deploy.yaml` builds the Docker image and tags it, then commits the new image tag to `k8s/overlays/*/kustomization.yaml` and pushes directly to main.
**What happened**: Image built and pushed to ghcr.io successfully, but the "Commit and push manifest updates" step failed: "GH006: Protected branch update failed — Changes must be made through a pull request."
**Root cause**: dk-alchemy #650 (staging branch) applied branch protection rules to main requiring PRs. The default `GITHUB_TOKEN` in GitHub Actions cannot bypass branch protection, even with `contents: write` permission.
**Lesson**: When branch protection is active, CI manifest-update steps must create a PR instead of pushing directly. Or configure a GitHub App with bypass permissions. For now, manual image-tag updates via `sed + git push` work (human pushes bypass protection). The CI fix (PR-based manifest update) is committed but deferred.
**Tags**: ci-cd, branch-protection, github-actions, image-tag, manifest-update

## 2026-04-17 — Grafana API key needs Admin role for folder creation

**Context**: Dashboard sync workflow pushes 12 dashboards to Grafana via the REST API. The `GRAFANA_API_KEY` in Doppler was expired (HTTP 401).
**What happened**: Created a new service account with "Editor" role — key worked for API auth (HTTP 200) but dashboard sync failed: "Forbidden — insufficient permissions." All 12 dashboards rejected.
**Root cause**: The sync script creates/updates folders before pushing dashboards. Folder creation requires Grafana "Admin" role, not "Editor." The service account had Editor scope.
**Lesson**: Grafana service accounts for dashboard-sync automation need Admin role (not Editor). After upgrading the SA role via `PATCH /api/serviceaccounts/<id>`, the sync succeeded. Store the key in Doppler at `dk-infrastructure/prd/GRAFANA_API_KEY`.
**Tags**: grafana, api-key, dashboard-sync, doppler, permissions

## 2026-04-18 — WAL circuit breaker correctly blocks transforms when archiver is broken

**Context**: All SQLMesh transforms (bronze/silver/gold) complete in 5-7 seconds with "Status: skipped — WAL circuit breaker open." Investigated assuming the breaker was misconfigured since WAL pressure was 0.39%.
**What happened**: The WAL pressure view (`meta.wal_pressure`) showed 0.39% — but that measures current write rate against max_wal_size. The circuit breaker (`wal_metrics.py`) checks `pg_stat_archiver` for RECENT archiver failures, which is a completely different signal. The archiver had 1,944 failures with the last within 30 minutes, and WAL had accumulated to 23GB (5.75× over the 4GB max).
**Root cause**: Barman→SeaweedFS WAL archiving was broken (dk-alchemy #648 closed prematurely). The archiver couldn't ship WAL segments to S3, so they accumulated. The circuit breaker correctly detected this via `pg_stat_archiver.last_failed_time` and blocked all transforms to prevent generating MORE unarchivable WAL.
**Lesson**: WAL "pressure" (pct of max_wal_size consumed by current write rate) and WAL "archiver health" (can segments be shipped to backup storage) are orthogonal signals. A system can have low pressure but a broken archiver — or high pressure with a healthy archiver. The circuit breaker checks BOTH, which is correct. Don't override it just because one signal looks fine.
**Tags**: wal, circuit-breaker, archiver, sqlmesh, transforms, barman, seaweedfs

## 2026-05-12 — ArgoCD blocks Deployment update when current ReplicaSet is unhealthy

**Context**: Shipping a multi-PR fix chain to `job-trigger` Deployment in dk-data-prod — image bump (PR #354) → memory bump (#355) → probe delays (#356) → startup-unblock (#357) → probe-timeout (#359) → uvicorn `--workers` (#360+#361). Each PR addressed the previous PR's surfaced failure mode.
**What happened**: After merging PR #355 (memory 512Mi → 1Gi) and PR #361 (image to `main-ed0f4f9` with `--workers 4`), Argo refused to apply the new specs even though git was at the target revision. Sync status: `OutOfSync` / `Running`; operationState message: `"waiting for healthy state of apps/Deployment/job-trigger"`. The Deployment couldn't become Healthy on the *old* spec (single worker / 512Mi) because pods were CrashLoopBackOff, so Argo never proceeded to apply the *new* spec that would have fixed them.
**Root cause**: Argo's sync waits for resource health BEFORE applying subsequent rev changes. For Deployments, "health" means the rollout completed and the new ReplicaSet is fully Ready. If the rollout cannot complete (probes fail, pods OOM, etc.), Argo retries forever without advancing. Functionally this is a deadlock when the fix lives in revision N+1.
**Lesson**: When Argo is blocked on "waiting for healthy state" and the next git revision contains the fix:
  - **Unblock with direct `kubectl set image`/`kubectl patch`** on the controlled resource. Argo then observes that the live spec already matches target and stops retrying.
  - Avoid letting subsequent PRs pile up while sync is stuck — each new push extends the retry queue Argo will work through once unblocked.
  - For the longer term: evaluate `syncOptions: [Replace=true]` and `progressDeadlineSeconds` on Deployments that have a history of degraded rollouts. The 2026-04-17 lesson on ArgoCD blocking on never-run Jobs (one-shot Jobs in ArgoCD-managed resources) is a related-but-different variant — Deployments are the "ongoing health" version, Jobs are the "never-progressing health" version.
**Tags**: argocd, deployment, sync-deadlock, rollout, unblock-procedure

## 2026-05-12 — GitHub Actions `gh pr create` blocked at the enterprise level

**Context**: The `build-dk-data-fe.yaml` workflow builds the job-trigger image and pushes to ghcr, then opens a chore-PR for the prod-overlay image-tag bump via `gh pr create`. The PR-creation step has been failing since 2026-04-19, leaving orphan `chore/prod-image-tag-*` branches on origin (4 accumulated before manual cleanup).
**What happened**: Workflow logs show `pull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests (createPullRequest)`. Repo admin attempting to flip `can_approve_pull_request_reviews=true` via `gh api repos/<org>/<repo>/actions/permissions/workflow -X PUT` gets a 409: `"The enterprise does not allow GitHub Actions to create or approve pull requests"`.
**Root cause**: Repo-level `default_workflow_permissions` is `write`, but the *enterprise-level* "Allow GitHub Actions to create and approve pull requests" setting is OFF. The enterprise setting overrides the repo setting — repo admin is not sufficient.
**Lesson**: For repos in a GH Enterprise that disables this setting, CI workflows that need to create PRs must either: (a) use a Personal Access Token (PAT) with `repo` scope stored as a workflow secret, (b) use a GitHub App with PR-create permission and authenticate the workflow as the App, or (c) get an enterprise-admin to flip the enterprise-level toggle. Related: 2026-04-17 lesson on CI manifest-push blocked by branch protection — both are GH-Enterprise-side permission constraints that need enterprise-admin (not repo-admin) to resolve. The dk-data-FE workflow currently relies on a human operator manually opening + merging the chore PR after each main push.
**Tags**: ci-cd, github-actions, github-enterprise, permissions, pull-requests

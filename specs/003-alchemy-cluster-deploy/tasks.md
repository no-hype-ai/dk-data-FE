# Tasks: dk-alchemy Cluster Deployment

**Input**: Design documents from `/specs/003-alchemy-cluster-deploy/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not requested in feature specification. Test tasks omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Directory Structure & Cleanup)

**Purpose**: Create target directory structure and remove obsolete paths

- [x] T001 Create `k8s/base/postgrest/`, `k8s/base/ingestion/`, `k8s/overlays/prod/`, `k8s/overlays/staging/` directory structure
- [x] T002 Create `.gitops/prod/apps/` and `.gitops/staging/apps/` directory structure
- [x] T003 Remove obsolete `.gitops/base/`, `.gitops/overlays/`, `.gitops/argocd/`, and `k8s/postgrest/` directories after manifest migration is complete (execute at end of Phase 2)

---

## Phase 2: Foundational (Manifest Consolidation & GitOps Restructure)

**Purpose**: Migrate all Kubernetes resources to `k8s/base/` and ArgoCD definitions to `.gitops/{env}/apps/`. MUST be complete before any user story work.

**CRITICAL**: No user story work can begin until this phase is complete.

### PostgREST manifests

- [x] T004 [P] Migrate PostgREST deployment to `k8s/base/postgrest/deployment.yaml` — copy from `.gitops/base/postgrest/deployment.yaml`, remove hardcoded `namespace: tavr-data`, update image to `postgrest/postgrest:v12.2.3`, update secret references from `dk-data-fe-secrets` to `dk-data-secrets`
- [x] T005 [P] Migrate PostgREST service to `k8s/base/postgrest/service.yaml` — copy from `.gitops/base/postgrest/service.yaml`, remove hardcoded namespace
- [x] T006 [P] Migrate PostgREST configmap to `k8s/base/postgrest/configmap.yaml` — copy from `.gitops/base/postgrest/configmap.yaml`, set `PGRST_DB_SCHEMAS` to `api`, set `PGRST_DB_ANON_ROLE` to `web_anon`, remove hardcoded namespace

### Ingestion manifests

- [x] T007 [P] Migrate Job Trigger deployment to `k8s/base/ingestion/job-trigger-deployment.yaml` — copy from `.gitops/base/ingestion/job-trigger-deployment.yaml`, remove hardcoded namespace, update image to `ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:latest`, include ServiceAccount, Role, and RoleBinding in same file
- [x] T008 [P] Migrate Job Trigger service to `k8s/base/ingestion/job-trigger-service.yaml` — copy from `.gitops/base/ingestion/job-trigger-service.yaml`, remove hardcoded namespace, set port 8000
- [x] T009 [P] Migrate CMS CronJob to `k8s/base/ingestion/cronjob-cms-all.yaml` — copy from `.gitops/base/ingestion/cronjob-cms-all.yaml`, remove hardcoded namespace, update image reference to GHCR, set schedule `0 2 * * 0` (Sunday 2 AM)
- [x] T010 [P] Migrate catalog refresh CronJob to `k8s/base/ingestion/cronjob-refresh.yaml` — copy from `.gitops/base/catalog/cronjob-refresh.yaml`, remove hardcoded namespace, update image reference to GHCR, set schedule `0 6 * * *` (daily 6 AM)

### Kustomize base & overlays

- [x] T011 Create `k8s/base/kustomization.yaml` — list all resources: `postgrest/deployment.yaml`, `postgrest/service.yaml`, `postgrest/configmap.yaml`, `ingestion/job-trigger-deployment.yaml`, `ingestion/job-trigger-service.yaml`, `ingestion/cronjob-cms-all.yaml`, `ingestion/cronjob-refresh.yaml`, `db-init-job.yaml`, `ingress.yaml`, `middleware-rate-limit.yaml`, `networkpolicy.yaml`, `doppler-secret.yaml`, `service-monitor.yaml`, `alert-rules.yaml`
- [x] T012 [P] Create `k8s/overlays/prod/kustomization.yaml` — namespace `dk-data-prod`, 3 PostgREST replicas, 2 Job Trigger replicas, prod resource limits, reference base `../../base`, NO `namePrefix`, patch Doppler config to `prd`
- [x] T013 [P] Create `k8s/overlays/staging/kustomization.yaml` — namespace `dk-data-staging`, 2 PostgREST replicas, 1 Job Trigger replica, staging resource limits, reference base `../../base`, NO `namePrefix`, patch Doppler config to `stg`, patch Ingress host to `data.preview.behaviorlabs.ai`

### ArgoCD definitions (`.gitops/`)

- [x] T014 [P] Create `.gitops/prod/apps/namespace.yaml` — Namespace `dk-data-prod` with labels `tenant: dk-data`, `environment: production`
- [x] T015 [P] Create `.gitops/prod/apps/project.yaml` — ArgoCD AppProject `dk-data` allowing destinations `dk-data-prod` namespace, source repo `https://github.com/data-kinetic-projects/dk-data-FE.git`, clusterResourceWhitelist for Namespace, permit all namespaced resources
- [x] T016 [P] Create `.gitops/prod/apps/application.yaml` — ArgoCD Application `dk-data-prod` in project `dk-data`, source path `k8s/overlays/prod`, targetRevision `main`, destination namespace `dk-data-prod`, automated sync with prune and selfHeal, retry on failure
- [x] T017 [P] Create `.gitops/prod/apps/kustomization.yaml` — list resources: `namespace.yaml`, `project.yaml`, `application.yaml`
- [x] T018 [P] Create `.gitops/staging/apps/namespace.yaml` — Namespace `dk-data-staging` with labels `tenant: dk-data`, `environment: staging`
- [x] T019 [P] Create `.gitops/staging/apps/project.yaml` — ArgoCD AppProject `dk-data` for staging, allowing `dk-data-staging` namespace
- [x] T020 [P] Create `.gitops/staging/apps/application.yaml` — ArgoCD Application `dk-data-staging` in project `dk-data`, source path `k8s/overlays/staging`, targetRevision `staging`, destination namespace `dk-data-staging`
- [x] T021 [P] Create `.gitops/staging/apps/kustomization.yaml` — list resources: `namespace.yaml`, `project.yaml`, `application.yaml`

### Cleanup

- [x] T022 Execute cleanup from T003: delete `.gitops/base/`, `.gitops/overlays/`, `.gitops/argocd/`, `.gitops/README.md`, `.gitops/base/namespace.yaml`, and `k8s/postgrest/` after verifying all manifests have been migrated to `k8s/base/`

**Checkpoint**: All manifests consolidated in `k8s/base/` with Kustomize overlays. ArgoCD definitions in `.gitops/{env}/apps/`. Old directories removed. Ready for user story implementation.

---

## Phase 3: User Story 1 — Data API Reachable at Production Domain (Priority: P1) MVP

**Goal**: PostgREST API is publicly accessible at `https://data.behaviorlabs.ai` (prod) and `https://data.preview.behaviorlabs.ai` (staging) with TLS and rate limiting.

**Independent Test**: `curl -s https://data.behaviorlabs.ai/` returns HTTP 200 with JSON OpenAPI schema. `curl -s https://data.preview.behaviorlabs.ai/` returns the same for staging.

- [x] T023 [US1] Create `k8s/base/ingress.yaml` — standard `networking.k8s.io/v1` Ingress resource named `dk-data-api` with: `ingressClassName: traefik`, host `data.behaviorlabs.ai`, TLS with `cert-manager.io/cluster-issuer: letsencrypt-prod` annotation, `traefik.ingress.kubernetes.io/router.entrypoints: websecure`, `traefik.ingress.kubernetes.io/router.tls: "true"`, path `/` → service `postgrest` port 3000, reference rate-limit middleware via `traefik.ingress.kubernetes.io/router.middlewares: $(NAMESPACE)-dk-data-rate-limit@kubernetescrd`
- [x] T024 [US1] Create `k8s/base/middleware-rate-limit.yaml` — Traefik Middleware CRD named `dk-data-rate-limit` with `rateLimit.average: 100`, `rateLimit.burst: 50`, `rateLimit.period: 1m` (per contract: 100 req/min per IP, 50 burst)
- [x] T025 [US1] Add staging host patch in `k8s/overlays/staging/kustomization.yaml` — JSON patch to replace Ingress host from `data.behaviorlabs.ai` to `data.preview.behaviorlabs.ai` and TLS secretName accordingly
- [x] T026 [US1] Verify PostgREST deployment in `k8s/base/postgrest/deployment.yaml` has liveness probe (`httpGet /` port 3000, periodSeconds 10) and readiness probe (`httpGet /` port 3000, initialDelaySeconds 5, periodSeconds 5) — add if missing

**Checkpoint**: Ingress, TLS, and rate limiting configured. PostgREST accessible at both domains once ArgoCD syncs.

---

## Phase 4: User Story 2 — ArgoCD Manages Full Deployment Lifecycle (Priority: P1)

**Goal**: ArgoCD automatically detects and syncs dk-data-fe from the app-of-apps bootstrap in dk-alchemy.

**Independent Test**: Modify a ConfigMap value, push to `main`, and observe ArgoCD auto-sync to `dk-data-prod` namespace.

**Note**: This phase produces manifests for the dk-alchemy repository (external). These files must be committed to the dk-alchemy repo at `/Users/nicholas/Code/dk-alchemy`.

- [x] T027 [P] [US2] Create `dk-alchemy:.gitops/external/dk-data-fe.yaml` — two ArgoCD Application resources: `dk-data-bootstrap-prod` (source `.gitops/prod/apps`, targetRevision `main`) and `dk-data-bootstrap-staging` (source `.gitops/staging/apps`, targetRevision `staging`), both in project `dk-data-bootstrap`, automated sync with prune and selfHeal, labels `tenant: dk-data`
- [x] T028 [P] [US2] Create `dk-alchemy:.gitops/repositories/dk-data-bootstrap-project.yaml` — minimal ArgoCD AppProject `dk-data-bootstrap` allowing only `argoproj.io/Application` and `argoproj.io/AppProject` cluster resources, source `https://github.com/data-kinetic-projects/dk-data-FE.git`
- [x] T029 [US2] Update `dk-alchemy:.gitops/external/kustomization.yaml` — add `dk-data-fe.yaml` to resources list
- [x] T030 [US2] Update `dk-alchemy:.gitops/repositories/kustomization.yaml` — add `dk-data-bootstrap-project.yaml` to resources list
- [x] T031 [US2] Verify `.gitops/prod/apps/application.yaml` and `.gitops/staging/apps/application.yaml` (created in T016/T020) include `syncPolicy.automated.prune: true`, `syncPolicy.automated.selfHeal: true`, and `syncPolicy.retry.limit: 5`

**Checkpoint**: dk-alchemy bootstrap Applications point to dk-data-fe repo. ArgoCD will detect and auto-sync both environments.

---

## Phase 5: User Story 3 — PostgREST Connects to Shared CNPG PostgreSQL (Priority: P1)

**Goal**: PostgREST and Job Trigger connect to the shared CNPG cluster using a dedicated `dk_data` database with proper roles and Doppler-managed secrets.

**Independent Test**: Deploy PostgREST and verify `curl http://postgrest.dk-data-prod.svc.cluster.local:3000/data_catalog` returns data from the `api` schema.

- [x] T032 [P] [US3] Create `k8s/base/doppler-secret.yaml` — DopplerSecret CRD named `dk-data-secrets`, project `dk-data`, config `prd` (patched to `stg` in staging overlay), tokenSecretRef `doppler-token-secret`, resyncSeconds 300, managedSecretRef name `dk-data-secrets`
- [x] T033 [P] [US3] Create `k8s/base/db-init-job.yaml` — Kubernetes Job named `db-init` with: image `postgres:16.4`, annotation `argocd.argoproj.io/sync-wave: "-1"` and `argocd.argoproj.io/hook: Sync`, `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`, env vars from `dk-data-secrets` (POSTGRES_HOST, POSTGRES_PASSWORD), inline SQL script that: (a) creates database `dk_data` if not exists, (b) creates schemas `raw`, `staging`, `mart`, `scoring`, `meta`, `api`, (c) creates roles `authenticator` (LOGIN, NOINHERIT), `web_anon`, `analyst`, `api_user`, `readonly`, (d) grants role hierarchy (authenticator can SET ROLE to web_anon/analyst/api_user), (e) grants SELECT on api tables per role per data-model.md, (f) sets default privileges, (g) revokes CONNECT on database `behavior_labs` from `authenticator` and `readonly`. SQL must be fully idempotent using `IF NOT EXISTS` and `DO $$ ... $$` blocks. Reference `src/dk_data/sql/migrations/002_role_restrictions.sql` for existing permission patterns.
- [x] T034 [US3] Update `k8s/base/postgrest/deployment.yaml` — ensure env vars reference `dk-data-secrets` secret: `PGRST_DB_URI` constructed from `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `PGRST_JWT_SECRET` from secret. Verify `PGRST_DB_SCHEMAS=api` and `PGRST_DB_ANON_ROLE=web_anon` are set.
- [x] T035 [US3] Update `k8s/base/ingestion/job-trigger-deployment.yaml` — ensure env vars for database connection reference `dk-data-secrets` secret (same keys as PostgREST)
- [x] T036 [US3] Add Doppler config patch to `k8s/overlays/staging/kustomization.yaml` — patch DopplerSecret config from `prd` to `stg`

**Checkpoint**: Database init Job creates `dk_data` database and roles. PostgREST and Job Trigger connect via Doppler-managed secrets. Staging uses separate Doppler config.

---

## Phase 6: User Story 4 — Other Cluster Apps Can Query dk-data (Priority: P2)

**Goal**: Cross-app access to PostgREST via internal service DNS, enforced by NetworkPolicy.

**Independent Test**: From a pod in `behaviorlabs-prod` namespace, `curl http://postgrest.dk-data-prod.svc.cluster.local:3000/data_catalog` returns data.

- [x] T037 [P] [US4] Create `k8s/base/networkpolicy.yaml` — four NetworkPolicy resources per `specs/003-alchemy-cluster-deploy/contracts/networkpolicy.yaml`: (1) `dk-data-default-deny` (deny all ingress+egress), (2) `dk-data-postgrest-ingress` (allow from kube-system, behaviorlabs-prod, behaviorlabs-staging, agentmesh-prod, agentmesh-staging, infra on port 3000), (3) `dk-data-job-trigger-ingress` (allow same-namespace + infra on port 8000), (4) `dk-data-egress` (allow DNS on 53, PostgreSQL on 5432 to infra, OTLP on 4317 to infra, external HTTPS on 443 excluding RFC1918)
- [x] T038 [US4] Update `dk-alchemy:k8s/infrastructure/postgres/base/networkpolicy.yaml` — add `dk-data-prod` and `dk-data-staging` namespaces to ingress allowlist on port 5432 so dk-data pods can reach the shared CNPG cluster

**Checkpoint**: Zero-trust networking enforced. Approved namespaces can reach PostgREST. Unapproved namespaces are blocked. dk-data can reach PostgreSQL and OTLP.

---

## Phase 7: User Story 5 — Observability Data Flows to Shared LGTM Stack (Priority: P2)

**Goal**: Metrics, logs, and traces from dk-data services flow to the shared Alloy collector and are visible in Grafana.

**Independent Test**: Query Loki in Grafana for `{namespace="dk-data-prod"}` and see structured JSON logs.

- [x] T039 [P] [US5] Fix OTLP endpoint in `src/dk_data/observability/__init__.py` — change default from `alloy.monitoring:4317` to `alloy.infra.svc.cluster.local:4317`
- [x] T040 [P] [US5] Update `k8s/base/ingestion/job-trigger-deployment.yaml` — set `OTEL_EXPORTER_OTLP_ENDPOINT` env var to `http://alloy.infra.svc.cluster.local:4317`
- [x] T041 [P] [US5] Create `k8s/base/service-monitor.yaml` — ServiceMonitor `dk-data-postgrest` (selector `app: postgrest`, port 3000, path `/`), ServiceMonitor `dk-data-job-trigger` (selector `app: job-trigger`, port 8000, path `/metrics`), PodMonitor `dk-data-cronjobs` (selector `app: cronjob`, port 8000, path `/metrics`). Use namespace-agnostic selectors (namespace set by overlay).
- [x] T042 [P] [US5] Create `k8s/base/alert-rules.yaml` — PrometheusRule `dk-data-alerts` with rules: (1) data staleness > 48h, (2) PostgREST error rate > 5% for 5m, (3) Job Trigger pod not ready for 5m, (4) batch job failure count > 2 in 1h, (5) CronJob missed schedule, (6) Pod memory > 80% of limit

**Checkpoint**: OTLP endpoint corrected. ServiceMonitors and PodMonitors configured. Alert rules defined. Telemetry flows to shared LGTM stack.

---

## Phase 8: User Story 6 — Secrets Managed via Doppler (Priority: P2)

**Goal**: All secrets managed via Doppler. Zero hardcoded credentials in repository.

**Independent Test**: `grep -r 'password\|secret\|api_key' k8s/ .gitops/ --include='*.yaml' -i` returns only secretKeyRef references, never plaintext values.

- [x] T043 [US6] Audit all YAML manifests in `k8s/base/` and `.gitops/` for hardcoded credentials — replace any plaintext values with `secretKeyRef` to `dk-data-secrets`. Verify `.gitops/base/postgrest/secret.yaml` content is NOT migrated (Doppler replaces it entirely).
- [x] T044 [US6] Verify `k8s/base/doppler-secret.yaml` (created in T032) uses correct dk-alchemy conventions: `tokenSecret.name: doppler-token-secret`, `managedSecret.name: dk-data-secrets`, `managedSecret.type: Opaque`
- [x] T045 [US6] Verify `.gitleaks.toml` at repository root covers all secret patterns — ensure it detects JWT secrets, database passwords, API keys. File already exists; verify coverage.

**Checkpoint**: Zero hardcoded credentials. All sensitive values flow through Doppler → DopplerSecret → Kubernetes Secret → pod env vars.

---

## Phase 9: User Story 7 — Container Images Built and Published Automatically (Priority: P3)

**Goal**: CI pipeline builds and pushes Job Trigger Docker image to GHCR on every push to `main` or `staging`.

**Independent Test**: Push a change to `main`, observe GitHub Actions build, verify image at `ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:<sha>`.

- [x] T046 [P] [US7] Create `Dockerfile` at repository root — multi-stage build: (1) builder stage from `python:3.11-slim`, install build deps (`gcc`, `libpq-dev`), copy `pyproject.toml` and `uv.lock`, install dependencies via `pip install .`, (2) runtime stage from `python:3.11-slim`, install `libpq5`, copy installed packages and `src/dk_data/` from builder, create non-root user `appuser`, set `ENTRYPOINT ["uvicorn", "dk_data.ingestion.batch.api:app", "--host", "0.0.0.0", "--port", "8000"]`
- [x] T047 [P] [US7] Create `.github/workflows/build-push.yaml` — trigger on push to `main` and `staging`, steps: checkout, login to GHCR via `docker/login-action`, build and push via `docker/build-push-action` with tags `ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:<branch>-<sha7>` and `latest` for main branch. Use `GITHUB_TOKEN` for GHCR auth.
- [x] T048 [US7] Update `k8s/base/ingestion/job-trigger-deployment.yaml` — set image to `ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:latest`, add `imagePullSecrets` referencing GHCR credentials secret
- [x] T049 [US7] Update `k8s/base/ingestion/cronjob-cms-all.yaml` and `k8s/base/ingestion/cronjob-refresh.yaml` — set image to same GHCR image as Job Trigger, add `imagePullSecrets`

**Checkpoint**: Dockerfile and CI pipeline in place. Job Trigger image builds and pushes automatically. Deployment and CronJob manifests reference GHCR image.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, cleanup, and documentation updates

- [x] T050 Validate all `k8s/base/` manifests render correctly with `kubectl kustomize k8s/overlays/prod` and `kubectl kustomize k8s/overlays/staging` — fix any Kustomize errors
- [x] T051 Validate all `.gitops/prod/apps/` and `.gitops/staging/apps/` manifests render correctly with `kubectl kustomize .gitops/prod/apps` and `kubectl kustomize .gitops/staging/apps`
- [x] T052 [P] Update `.dockerignore` — exclude `.gitops/`, `specs/`, `tests/`, `.git/`, `*.md`, `.specify/`, `.gitleaks.toml` to minimize Docker build context
- [x] T053 [P] Update `.env.example` — add all environment variables referenced by manifests (POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, PGRST_JWT_SECRET, OTEL_EXPORTER_OTLP_ENDPOINT) with placeholder values
- [x] T054 Run quickstart.md validation — verify Steps 1-3 (Doppler setup, dk-alchemy bootstrap, image build) documentation matches actual manifest paths and resource names created in implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — create directory structure first
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1 - Public API)**: Depends on Phase 2 — creates Ingress and rate limiting
- **Phase 4 (US2 - ArgoCD)**: Depends on Phase 2 — creates dk-alchemy bootstrap manifests
- **Phase 5 (US3 - Database)**: Depends on Phase 2 — creates db-init Job and Doppler secret
- **Phase 6 (US4 - Cross-App)**: Depends on Phase 2 — creates NetworkPolicy
- **Phase 7 (US5 - Observability)**: Depends on Phase 2 — creates ServiceMonitors and fixes OTLP
- **Phase 8 (US6 - Secrets)**: Depends on Phase 5 (Doppler secret created in T032) — audit and harden
- **Phase 9 (US7 - CI/Docker)**: Depends on Phase 2 — creates Dockerfile and CI pipeline
- **Phase 10 (Polish)**: Depends on all previous phases

### User Story Dependencies

- **US1 (Public API)**: Independent after Phase 2. No dependency on other stories.
- **US2 (ArgoCD)**: Independent after Phase 2. External repo (dk-alchemy) changes.
- **US3 (Database)**: Independent after Phase 2. Creates database init and Doppler secret.
- **US4 (Cross-App)**: Independent after Phase 2. External repo (dk-alchemy) NetworkPolicy change in T038.
- **US5 (Observability)**: Independent after Phase 2. Only Python source change in T039.
- **US6 (Secrets)**: Depends on US3 (T032 creates DopplerSecret). Audit and validation.
- **US7 (CI/Docker)**: Independent after Phase 2. Creates Dockerfile and CI pipeline.

### Within Each User Story

- Resources created in order: CRDs → ConfigMaps/Secrets → Services → Deployments → Ingress
- Parallel tasks (marked [P]) can run simultaneously within a story

### Parallel Opportunities

**After Phase 2 completes, the following stories can proceed in parallel:**

- US1 (Ingress) + US2 (ArgoCD) + US3 (Database) + US4 (NetworkPolicy) + US5 (Observability) + US7 (CI/Docker)
- US6 (Secrets audit) starts after US3 completes

---

## Parallel Example: Phase 2 (Foundational)

```text
# All PostgREST manifests in parallel:
T004: Migrate PostgREST deployment to k8s/base/postgrest/deployment.yaml
T005: Migrate PostgREST service to k8s/base/postgrest/service.yaml
T006: Migrate PostgREST configmap to k8s/base/postgrest/configmap.yaml

# All Ingestion manifests in parallel:
T007: Migrate Job Trigger deployment to k8s/base/ingestion/job-trigger-deployment.yaml
T008: Migrate Job Trigger service to k8s/base/ingestion/job-trigger-service.yaml
T009: Migrate CMS CronJob to k8s/base/ingestion/cronjob-cms-all.yaml
T010: Migrate catalog refresh CronJob to k8s/base/ingestion/cronjob-refresh.yaml

# All ArgoCD definitions in parallel:
T014-T021: All .gitops/{env}/apps/ files
```

## Parallel Example: User Stories After Phase 2

```text
# These 6 stories can execute simultaneously:
US1: T023-T026 (Ingress + rate limiting)
US2: T027-T031 (ArgoCD bootstrap in dk-alchemy)
US3: T032-T036 (Database + Doppler)
US4: T037-T038 (NetworkPolicy)
US5: T039-T042 (Observability)
US7: T046-T049 (Dockerfile + CI)

# Then after US3 completes:
US6: T043-T045 (Secrets audit)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3)

1. Complete Phase 1: Setup (directory structure)
2. Complete Phase 2: Foundational (manifest consolidation)
3. Complete Phase 3: US1 (Ingress + rate limiting) — API reachable
4. Complete Phase 4: US2 (ArgoCD bootstrap) — automated deployment
5. Complete Phase 5: US3 (Database + Doppler) — data served
6. **STOP and VALIDATE**: Deploy to staging, verify PostgREST serves data at `data.preview.behaviorlabs.ai`

### Incremental Delivery

1. Setup + Foundational → Manifests consolidated
2. US1 + US2 + US3 → MVP: API serves data via ArgoCD (Deploy/Validate)
3. US4 → Cross-app access enabled (Deploy/Validate)
4. US5 → Observability flows to Grafana (Deploy/Validate)
5. US6 → Secrets audit passes (Deploy/Validate)
6. US7 → CI pipeline builds images automatically (Deploy/Validate)
7. Polish → All manifests validated, docs updated

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- dk-alchemy changes (T027-T030, T038) must be committed to the dk-alchemy repository separately
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence

# Feature Specification: dk-alchemy Cluster Deployment

**Feature Branch**: `003-alchemy-cluster-deploy`
**Created**: 2026-01-28
**Status**: Draft
**Input**: User description: "Deploy dk-data-fe to dk-alchemy cluster under data.behaviorlabs.ai and data.preview.behaviorlabs.ai, integrating with shared CNPG PostgreSQL, Doppler secrets, Traefik ingress, LGTM observability stack, and ArgoCD GitOps app-of-apps pattern. Restructure manifests, fix mismatches, and enable cross-app data access."

## Clarifications

### Session 2026-01-28

- Q: Should the Job Trigger service be exposed via the public Ingress, or kept internal-only? → A: Internal-only. Job Trigger is accessible only via ClusterIP within the cluster (no Ingress path). Only PostgREST is exposed publicly.
- Q: Which namespaces should be in the initial NetworkPolicy allowlist? → A: `behaviorlabs-prod`, `behaviorlabs-staging`, `agentmesh-prod`, and `agentmesh-staging`. Additional namespaces added on request.
- Q: Should the `dk_data` database and roles be initialized via an automated Kubernetes Job or a manual runbook? → A: Kubernetes Job. A Job manifest in `k8s/base/` runs SQL init scripts against the shared CNPG cluster. Idempotent and version-controlled.
- Q: Should the public Ingress include rate limiting? → A: Yes. 100 requests/minute per IP with 50-request burst allowance, enforced via Traefik middleware.
- Q: Should existing CronJob manifests (fetch-cms-all, catalog-refresh) be included in this deployment scope? → A: Yes. Migrate existing CronJob manifests to `k8s/base/` alongside Job Trigger deployment.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Data API Reachable at Production Domain (Priority: P1)

An operator deploys dk-data-fe to the dk-alchemy cluster. Once synced by ArgoCD, the PostgREST API is reachable at `https://data.behaviorlabs.ai` and the staging instance at `https://data.preview.behaviorlabs.ai`. External consumers can query the data catalog and authenticated endpoints via these URLs.

**Why this priority**: Without a functioning public endpoint under the correct domain, no consumer (internal or external) can access the data platform. This is the core deliverable.

**Independent Test**: Navigate to `https://data.behaviorlabs.ai/` in a browser or via `curl` and receive a valid OpenAPI schema response. Navigate to `https://data.preview.behaviorlabs.ai/` and receive the same for staging.

**Acceptance Scenarios**:

1. **Given** dk-data-fe manifests are merged to `main`, **When** ArgoCD syncs the production Application, **Then** `https://data.behaviorlabs.ai/` returns an HTTP 200 with a JSON OpenAPI schema.
2. **Given** dk-data-fe manifests are merged to `staging` branch, **When** ArgoCD syncs the staging Application, **Then** `https://data.preview.behaviorlabs.ai/` returns an HTTP 200 with a JSON OpenAPI schema.
3. **Given** a user requests a non-public endpoint without a JWT token, **When** the request reaches PostgREST, **Then** the response is limited to `web_anon` role permissions (health check, data catalog only).
4. **Given** TLS is configured, **When** a client connects via HTTPS, **Then** a valid Let's Encrypt certificate is presented for the requested domain.

---

### User Story 2 - ArgoCD Manages Full Deployment Lifecycle (Priority: P1)

A platform engineer pushes manifest changes to the dk-data-fe repository. ArgoCD automatically detects the change through the app-of-apps bootstrap pattern defined in dk-alchemy, syncs the Application resources, and deploys to the correct namespace without manual intervention.

**Why this priority**: GitOps-driven deployment is the foundation of dk-alchemy's operational model. Without correct ArgoCD integration, no automated deployment occurs.

**Independent Test**: Modify a configmap value in dk-data-fe, push to `main`, and observe ArgoCD automatically syncing the change to the `dk-data-prod` namespace within 3 minutes.

**Acceptance Scenarios**:

1. **Given** dk-alchemy has a bootstrap Application pointing to dk-data-fe's `.gitops/prod/apps`, **When** the bootstrap syncs, **Then** an AppProject and Application are created in the `argocd` namespace for dk-data production.
2. **Given** dk-alchemy has a bootstrap Application pointing to dk-data-fe's `.gitops/staging/apps`, **When** the bootstrap syncs, **Then** an AppProject and Application are created for dk-data staging.
3. **Given** the dk-data Application exists in ArgoCD, **When** a manifest change is pushed to the target branch, **Then** ArgoCD detects the drift and auto-syncs within 3 minutes.
4. **Given** a manifest introduces an invalid resource, **When** ArgoCD attempts to sync, **Then** the sync fails gracefully, the previous healthy state is preserved, and the failure is visible in ArgoCD UI.

---

### User Story 3 - PostgREST Connects to Shared CNPG PostgreSQL (Priority: P1)

PostgREST and the Job Trigger service connect to the shared CloudNativePG PostgreSQL cluster in the `infra` namespace using credentials managed by Doppler. A dedicated database (`dk_data`) isolates dk-data-fe's data from other applications sharing the same cluster.

**Why this priority**: Database connectivity is required for any data to be served. Using the shared cluster rather than a standalone instance is a hard requirement of the dk-alchemy architecture.

**Independent Test**: Deploy PostgREST and verify it connects to `postgresql.infra.svc.cluster.local:5432/dk_data` and responds to API queries returning data from the `api` schema.

**Acceptance Scenarios**:

1. **Given** the shared CNPG cluster is running and a `dk_data` database exists, **When** PostgREST starts, **Then** it connects using the `authenticator` role and serves the `api` schema.
2. **Given** Doppler syncs database credentials to the `dk-data-prod` namespace, **When** a pod references the managed secret, **Then** environment variables (`POSTGRES_HOST`, `POSTGRES_PASSWORD`, etc.) are populated correctly.
3. **Given** the `dk_data` database has `web_anon`, `analyst`, and `api_user` roles, **When** a JWT with `role: analyst` is sent, **Then** PostgREST grants read access to targets, scoring, and data source views only.
4. **Given** a network policy exists on the PostgreSQL pods, **When** a dk-data pod attempts to connect on port 5432, **Then** the connection is allowed (namespace is in the allowlist).

---

### User Story 4 - Other Cluster Apps Can Query dk-data (Priority: P2)

The BehaviorLabs API, Agent Mesh, or any other app deployed in dk-alchemy can access dk-data's PostgREST API via internal Kubernetes service DNS. Network policies explicitly allow traffic from approved namespaces. A read-only PostgreSQL role is available for apps needing direct SQL access.

**Why this priority**: Cross-app data access is the primary reason for deploying dk-data on the shared cluster rather than as an isolated service.

**Independent Test**: From a pod in the `behaviorlabs-prod` namespace, `curl http://postgrest.dk-data-prod.svc.cluster.local:3000/data_catalog` and receive a JSON response.

**Acceptance Scenarios**:

1. **Given** dk-data is deployed in `dk-data-prod`, **When** a pod in `behaviorlabs-prod` sends an HTTP request to `postgrest.dk-data-prod.svc.cluster.local:3000`, **Then** the request succeeds and returns data.
2. **Given** dk-data's NetworkPolicy allows ingress from `behaviorlabs-prod`, **When** a pod in an unapproved namespace attempts the same request, **Then** the connection is refused.
3. **Given** a read-only PostgreSQL role exists for the `dk_data` database, **When** an external app connects directly to the shared CNPG cluster using that role, **Then** it can SELECT from `api` and `mart` schemas but cannot INSERT, UPDATE, or DELETE.
4. **Given** the `PGRST_JWT_SECRET` is shared via Doppler with a consuming app, **When** that app generates a JWT with `role: api_user`, **Then** authenticated requests to dk-data's PostgREST succeed.

---

### User Story 5 - Observability Data Flows to Shared LGTM Stack (Priority: P2)

Metrics, logs, and traces from dk-data services are collected by the shared Alloy agent and routed to Mimir (metrics), Loki (logs), and Tempo (traces). Operators can view dk-data dashboards in the shared Grafana instance.

**Why this priority**: Observability is essential for operating dk-data in production, but the data platform can function without it initially.

**Independent Test**: After deploying dk-data, open Grafana at `grafana.behaviorlabs.ai`, query Loki for logs from the `dk-data-prod` namespace, and confirm structured JSON logs appear.

**Acceptance Scenarios**:

1. **Given** dk-data pods emit structured JSON logs to stdout, **When** Alloy scrapes the pod logs, **Then** logs are queryable in Grafana/Loki by namespace, pod, and service labels.
2. **Given** the Job Trigger exposes Prometheus metrics at `/metrics`, **When** Alloy scrapes the endpoint, **Then** metrics (request count, latency, job duration) are queryable in Grafana/Mimir.
3. **Given** the OpenTelemetry SDK sends traces to `alloy.infra.svc.cluster.local:4317`, **When** a request traverses PostgREST and the Job Trigger, **Then** a distributed trace is visible in Grafana/Tempo.
4. **Given** alert rules are defined in a PrometheusRule resource, **When** a condition triggers (e.g., data staleness > 48h), **Then** an alert fires and is visible in Grafana's alerting UI.

---

### User Story 6 - Secrets Are Managed via Doppler with No Hardcoded Credentials (Priority: P2)

All sensitive configuration (database passwords, JWT secrets, API keys) is stored in Doppler and synced to Kubernetes secrets via the Doppler operator. No credentials exist in source code, manifests, or environment variable defaults.

**Why this priority**: Security is non-negotiable for production, but initial development and testing can use manually provisioned secrets as a stopgap.

**Independent Test**: Inspect all YAML manifests in the repository and confirm zero hardcoded secrets. Deploy to staging and confirm pods start successfully using only Doppler-synced secrets.

**Acceptance Scenarios**:

1. **Given** a `dk-data` Doppler project with `prd` and `stg` configs, **When** the DopplerSecret CRD is applied, **Then** a Kubernetes secret is created in the target namespace with all required keys.
2. **Given** a Doppler token secret is pre-provisioned in the namespace, **When** the Doppler operator reconciles, **Then** application secrets are synced within 5 minutes.
3. **Given** a secret value is rotated in Doppler, **When** the resync interval elapses, **Then** the Kubernetes secret is updated and pods pick up the new value without manual restart.
4. **Given** a repository audit is performed, **When** scanning all files including git history, **Then** no plaintext credentials, API keys, or JWT secrets are found.

---

### User Story 7 - Container Images Are Built and Published Automatically (Priority: P3)

When code changes are pushed to the repository, a CI pipeline builds Docker images for the Job Trigger service and pushes them to the GitHub Container Registry (GHCR). Deployment manifests reference these images with content-addressable tags.

**Why this priority**: Image builds are a prerequisite for deploying the Job Trigger service but can initially be done manually or locally.

**Independent Test**: Push a code change to `main`, observe GitHub Actions build the image, and verify the new image tag appears in GHCR.

**Acceptance Scenarios**:

1. **Given** a Dockerfile exists for the Job Trigger service, **When** a push to `main` occurs, **Then** GitHub Actions builds and pushes the image to `ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:<sha>`.
2. **Given** the deployment manifest references a GHCR image, **When** ArgoCD syncs, **Then** pods pull the image successfully using the cluster's GHCR pull credentials.
3. **Given** the official PostgREST image is used directly (`postgrest/postgrest:v12.2.3`), **When** the deployment is created, **Then** no custom build is required for PostgREST.

---

### Edge Cases

- What happens when the shared CNPG cluster is temporarily unavailable? PostgREST and Job Trigger pods should fail readiness probes and stop receiving traffic until connectivity is restored.
- What happens when a Doppler token expires or is revoked? The Doppler operator stops syncing. Existing secrets remain until pods restart. Alert rules should detect when secrets become stale.
- What happens when the `dk_data` database does not yet exist during first deployment? PostgREST will fail to start. The database initialization Kubernetes Job must complete successfully before the main application pods are deployed. ArgoCD sync waves or manual Job execution can enforce ordering.
- What happens when a consuming app's namespace is not in the NetworkPolicy allowlist? The TCP connection to dk-data services is silently dropped. The consuming app must be explicitly added.
- What happens when the wildcard DNS record for `*.behaviorlabs.ai` is not yet propagated? External requests fail with DNS resolution errors. The dk-alchemy DDNS service manages this automatically but propagation takes up to 5 minutes (TTL 300s).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy PostgREST and Job Trigger services to `dk-data-prod` and `dk-data-staging` namespaces via ArgoCD auto-sync.
- **FR-002**: System MUST expose only the PostgREST API at `https://data.behaviorlabs.ai` (production) and `https://data.preview.behaviorlabs.ai` (staging) using standard Kubernetes Ingress resources with Traefik and valid TLS certificates. The Job Trigger service MUST NOT be exposed via public Ingress and MUST remain accessible only via internal ClusterIP service.
- **FR-003**: System MUST connect to the shared CloudNativePG PostgreSQL cluster at `postgresql.infra.svc.cluster.local:5432` using a dedicated `dk_data` database.
- **FR-004**: System MUST follow the dk-alchemy app-of-apps bootstrap pattern: bootstrap Application and AppProject defined in dk-alchemy, full AppProject and Application defined in dk-data-fe's `.gitops/prod/apps` and `.gitops/staging/apps` directories.
- **FR-005**: System MUST manage all secrets (database credentials, JWT secret, API keys) via Doppler, with a dedicated `dk-data` project and `prd`/`stg` configs following dk-alchemy naming conventions.
- **FR-006**: System MUST enforce zero-trust networking via NetworkPolicy resources, allowing ingress only from `kube-system` (Traefik), `infra`, `behaviorlabs-prod`, `behaviorlabs-staging`, `agentmesh-prod`, and `agentmesh-staging`. Additional namespaces may be added via manifest patches.
- **FR-007**: System MUST allow other cluster apps to access the PostgREST API via internal Kubernetes service DNS (`postgrest.dk-data-prod.svc.cluster.local:3000`), with explicit NetworkPolicy rules for each approved namespace.
- **FR-008**: System MUST provide a read-only PostgreSQL role for direct database consumers needing SQL access to `api` and `mart` schemas.
- **FR-009**: System MUST emit structured JSON logs, Prometheus metrics, and OpenTelemetry traces to the shared LGTM observability stack (Alloy at `alloy.infra.svc.cluster.local`).
- **FR-010**: System MUST build and publish Docker images for the Job Trigger service to GHCR via a CI pipeline, using content-addressable image tags.
- **FR-011**: System MUST consolidate all Kubernetes manifests into `k8s/base/` and `k8s/overlays/{prod,staging}/`, with `.gitops/` containing only ArgoCD Application/AppProject definitions.
- **FR-012**: System MUST initialize the `dk_data` database with required schemas (`raw`, `staging`, `mart`, `scoring`, `meta`, `api`), roles (`authenticator`, `web_anon`, `analyst`, `api_user`), and role permissions scoped only to the `dk_data` database. Initialization MUST be performed by an idempotent Kubernetes Job manifest in `k8s/base/` that runs SQL scripts against the shared CNPG cluster.
- **FR-013**: System MUST include PrometheusRule alert definitions for data freshness, API health, batch job failures, and resource utilization.
- **FR-014**: System MUST deploy with health probes (liveness and readiness) on all services so that unhealthy instances are automatically removed from service.
- **FR-015**: System MUST enforce rate limiting on the public PostgREST Ingress at 100 requests/minute per IP with a 50-request burst allowance, implemented via Traefik middleware.
- **FR-016**: System MUST include CronJob manifests for automated data refresh (`fetch-cms-all` weekly, `catalog-refresh` daily) in `k8s/base/`, migrated from the existing manifests and dependent on the Job Trigger container image.

### Key Entities

- **dk-data Namespace**: The Kubernetes namespace (`dk-data-prod` / `dk-data-staging`) where all dk-data-fe workloads run. Isolated from other app namespaces by NetworkPolicy.
- **PostgREST Service**: The auto-generated REST API that exposes PostgreSQL views from the `api` schema. Receives external traffic via Ingress and internal traffic via ClusterIP service.
- **Job Trigger Service**: A FastAPI application that triggers batch ingestion and transformation jobs. Runs as a Deployment with RBAC to create Kubernetes Jobs.
- **dk_data Database**: A dedicated PostgreSQL database within the shared CNPG cluster. Contains schemas: `raw`, `staging`, `mart`, `scoring`, `meta`, `api`. Owned by the `authenticator` role.
- **Bootstrap Application**: The ArgoCD Application in dk-alchemy that points to dk-data-fe's `.gitops/{env}/apps` directory and bootstraps the full deployment.
- **Doppler Project (dk-data)**: The secret management project containing environment-specific configs (`prd`, `stg`) with all credentials needed by dk-data services.
- **NetworkPolicy Allowlist**: The set of namespaces permitted to send traffic to dk-data services, managed via Kubernetes NetworkPolicy.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Production API at `https://data.behaviorlabs.ai` responds with HTTP 200 and valid content within 2 seconds of a request, with a valid TLS certificate.
- **SC-002**: Staging API at `https://data.preview.behaviorlabs.ai` responds with HTTP 200 and valid content within 2 seconds of a request, with a valid TLS certificate.
- **SC-003**: ArgoCD auto-syncs manifest changes from the repository to the cluster within 5 minutes of a push, with no manual intervention required.
- **SC-004**: At least one other cluster application (e.g., BehaviorLabs API) can successfully query dk-data's PostgREST API via internal service DNS and receive a valid data response.
- **SC-005**: Zero hardcoded credentials exist in the repository (verified by automated scan). All secrets are sourced from Doppler.
- **SC-006**: Structured logs from dk-data pods are queryable in Grafana/Loki within 1 minute of emission. Prometheus metrics are scrapeable and visible in Grafana/Mimir.
- **SC-007**: Database isolation is maintained: dk-data roles cannot access the `behavior_labs` database, and `behavior_labs` roles cannot access the `dk_data` database.
- **SC-008**: Unapproved namespaces cannot reach dk-data services (verified by attempting a connection from an unlisted namespace and confirming it is blocked).
- **SC-009**: CI pipeline builds and publishes a Docker image to GHCR on every push to `main`, and the image is pullable by the cluster.
- **SC-010**: The production deployment survives a single pod failure: with 3 PostgREST replicas, losing 1 pod does not cause downtime for API consumers.

## Assumptions

- The dk-alchemy cluster is operational with all shared services (CNPG, Traefik, Doppler operator, cert-manager, Alloy, ArgoCD) running and healthy.
- The GitHub repository `data-kinetic-projects/dk-data-FE` is accessible to ArgoCD via existing GHCR credentials in dk-alchemy.
- Wildcard DNS records for `*.behaviorlabs.ai` and `*.preview.behaviorlabs.ai` are managed by dk-alchemy's DDNS service and resolve to the cluster.
- The `staging` branch in dk-data-fe will be created and maintained alongside `main` for the dual-environment deployment model.
- Database initialization (creating `dk_data`, roles, schemas) is performed by a Kubernetes Job that must complete before the main application pods start. The Job is idempotent and safe to re-run.
- PostgREST uses the official Docker image (`postgrest/postgrest:v12.2.3`) and does not require a custom build.
- The Doppler project and service tokens will be provisioned as a manual prerequisite before deployment.
- Resource limits and replica counts follow dk-alchemy conventions: production runs 3 PostgREST replicas; staging runs 1-2.

## Scope Boundaries

### In Scope

- Restructuring dk-data-fe's `.gitops/` and `k8s/` directories to match dk-alchemy conventions
- Creating bootstrap Application and AppProject in dk-alchemy
- Configuring Ingress for `data.behaviorlabs.ai` and `data.preview.behaviorlabs.ai`
- Connecting to the shared CNPG PostgreSQL cluster with a dedicated database
- Configuring Doppler secret management with correct project and config naming
- Fixing NetworkPolicy to reference correct namespaces (`kube-system` for Traefik)
- Fixing OTLP endpoint to point to `alloy.infra.svc.cluster.local`
- Enabling cross-app access via NetworkPolicy allowlists and internal service DNS
- Creating a Dockerfile and CI pipeline for the Job Trigger service
- Creating database initialization Job/migration for `dk_data` database and roles
- Migrating CronJob manifests (fetch-cms-all, catalog-refresh) to `k8s/base/`
- Consolidating duplicate manifests between `.gitops/base/` and `k8s/`

### Out of Scope

- Metabase integration or BI dashboard deployment
- Per-PR preview environments (future dk-alchemy capability)
- Load testing or performance benchmarking
- Application-level test suite creation
- Database backup/restore automation (handled by CNPG operator in dk-alchemy)
- Changes to the dk-data-fe application logic (ingestion, transformation, API views)
- Multi-node pod anti-affinity (single-node K3s cluster)

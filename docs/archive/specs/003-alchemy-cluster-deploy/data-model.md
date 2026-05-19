# Data Model: dk-alchemy Cluster Deployment

**Branch**: `003-alchemy-cluster-deploy` | **Date**: 2026-01-28

This feature is infrastructure/deployment focused. The "data model" is the Kubernetes resource topology and the PostgreSQL role/schema structure within the shared CNPG cluster.

---

## 1. Kubernetes Resource Topology

### Namespace: `dk-data-prod` / `dk-data-staging`

| Resource Kind | Name | Purpose | Source |
|--------------|------|---------|--------|
| Deployment | `postgrest` | PostgREST API server (3 replicas prod, 2 staging) | `k8s/base/postgrest/deployment.yaml` |
| Service | `postgrest` | ClusterIP exposing port 3000 | `k8s/base/postgrest/service.yaml` |
| ConfigMap | `postgrest-config` | Non-secret PostgREST settings | `k8s/base/postgrest/configmap.yaml` |
| Deployment | `job-trigger` | FastAPI batch job management (2 replicas prod, 1 staging) | `k8s/base/ingestion/job-trigger-deployment.yaml` |
| Service | `job-trigger` | ClusterIP exposing port 8000 (internal only) | `k8s/base/ingestion/job-trigger-service.yaml` |
| ServiceAccount | `job-trigger` | RBAC identity for creating K8s Jobs | `k8s/base/ingestion/job-trigger-deployment.yaml` |
| Role | `job-creator` | Permissions: batch/jobs, batch/cronjobs, pods, pods/log | `k8s/base/ingestion/job-trigger-deployment.yaml` |
| RoleBinding | `job-trigger-can-create-jobs` | Binds job-trigger SA to job-creator Role | `k8s/base/ingestion/job-trigger-deployment.yaml` |
| CronJob | `fetch-cms-all` | Weekly CMS data fetch (Sunday 2 AM) | `k8s/base/ingestion/cronjob-cms-all.yaml` |
| CronJob | `catalog-refresh` | Daily catalog refresh (6 AM) | `k8s/base/ingestion/cronjob-refresh.yaml` |
| Job | `db-init` | One-time database initialization (sync wave 0) | `k8s/base/db-init-job.yaml` |
| Ingress | `dk-data-api` | Public PostgREST access via Traefik | `k8s/base/ingress.yaml` |
| Middleware | `dk-data-rate-limit` | 100 req/min per IP, 50 burst | `k8s/base/middleware-rate-limit.yaml` |
| NetworkPolicy | `dk-data-default-deny` | Zero-trust: deny all, allow listed | `k8s/base/networkpolicy.yaml` |
| DopplerSecret | `dk-data-secrets` | Syncs Doppler → K8s Secret | `k8s/base/doppler-secret.yaml` |
| ServiceMonitor | `dk-data-postgrest` | Prometheus scrape config for PostgREST | `k8s/base/service-monitor.yaml` |
| ServiceMonitor | `dk-data-job-trigger` | Prometheus scrape config for Job Trigger | `k8s/base/service-monitor.yaml` |
| PodMonitor | `dk-data-cronjobs` | Prometheus scrape for ephemeral CronJob pods | `k8s/base/service-monitor.yaml` |
| PrometheusRule | `dk-data-alerts` | Alert rules for freshness, health, jobs, resources | `k8s/base/alert-rules.yaml` |

### Namespace: `argocd` (managed by dk-alchemy)

| Resource Kind | Name | Purpose | Source |
|--------------|------|---------|--------|
| Application | `dk-data-bootstrap-prod` | Bootstrap → `.gitops/prod/apps` | dk-alchemy: `.gitops/external/dk-data-fe.yaml` |
| Application | `dk-data-bootstrap-staging` | Bootstrap → `.gitops/staging/apps` | dk-alchemy: `.gitops/external/dk-data-fe.yaml` |
| AppProject | `dk-data-bootstrap` | Minimal permissions for bootstrap | dk-alchemy: `.gitops/repositories/dk-data-bootstrap-project.yaml` |
| AppProject | `dk-data` | Full permissions for dk-data namespaces | dk-data-fe: `.gitops/{env}/apps/project.yaml` |
| Application | `dk-data-prod` | Points to `k8s/overlays/prod` | dk-data-fe: `.gitops/prod/apps/application.yaml` |
| Application | `dk-data-staging` | Points to `k8s/overlays/staging` | dk-data-fe: `.gitops/staging/apps/application.yaml` |

---

## 2. PostgreSQL Schema & Role Model

### Database: `dk_data` (within shared CNPG cluster)

```
dk_data
├── Schemas
│   ├── raw         — Raw ingested data (untransformed)
│   ├── staging     — Cleaned, deduplicated data
│   ├── mart        — Business logic aggregations
│   ├── scoring     — ML features and targeting scores
│   ├── meta        — Operational metadata (refresh_log, data_sources, batch_jobs, job_runs)
│   └── api         — Views exposed via PostgREST
│
├── Roles
│   ├── authenticator  — LOGIN role used by PostgREST connection
│   │   ├── GRANT web_anon   (SET ROLE for anonymous requests)
│   │   ├── GRANT analyst    (SET ROLE for analyst JWT)
│   │   └── GRANT api_user   (SET ROLE for api_user JWT)
│   │
│   ├── web_anon       — NOLOGIN: SELECT on api.data_catalog, api.health only
│   ├── analyst        — NOLOGIN: SELECT on api.targets, api.scoring, api.data_sources, api.data_catalog
│   ├── api_user       — NOLOGIN: SELECT on ALL TABLES in api schema (+ default privileges)
│   └── readonly       — NOLOGIN: SELECT on api.* and mart.* (for cross-app direct SQL)
│
└── Default Privileges
    └── ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO api_user
```

### Role Hierarchy

```
postgres (superuser, CNPG cluster owner)
└── authenticator (LOGIN, PostgREST connection role)
    ├── web_anon (anonymous — health + catalog)
    ├── analyst (read targets, scoring, data_sources)
    └── api_user (read all api tables)

readonly (separate LOGIN role for direct SQL consumers)
    └── SELECT on api.*, mart.*
```

### Key Constraints

- `authenticator` must have `NOINHERIT` so it doesn't get superuser privileges
- `authenticator` must be able to `SET ROLE` to `web_anon`, `analyst`, `api_user`
- `readonly` is a separate LOGIN role (not switchable via PostgREST JWT)
- All roles are scoped to the `dk_data` database only — no access to `behavior_labs`
- `REVOKE ALL ON DATABASE behavior_labs FROM authenticator, readonly` must be explicit

---

## 3. Secret Model

### Doppler Project: `dk-data`

| Secret Key | Config: prd | Config: stg | Consumer |
|-----------|-------------|-------------|----------|
| `POSTGRES_HOST` | `postgresql.infra.svc.cluster.local` | `postgresql.infra-staging.svc.cluster.local` | PostgREST, Job Trigger |
| `POSTGRES_PORT` | `5432` | `5432` | PostgREST, Job Trigger |
| `POSTGRES_USER` | `authenticator` | `authenticator` | PostgREST, Job Trigger |
| `POSTGRES_PASSWORD` | (generated) | (generated) | PostgREST, Job Trigger |
| `POSTGRES_DB` | `dk_data` | `dk_data` | PostgREST, Job Trigger |
| `PGRST_JWT_SECRET` | (256-bit secret) | (256-bit secret) | PostgREST |
| `ANTHROPIC_API_KEY` | (optional) | (optional) | Enrichment service |

### Kubernetes Secret Flow

```
Doppler SaaS (dk-data project, prd config)
  ↓ (DopplerSecret CRD, resync every 300s)
doppler-token-secret (pre-provisioned, contains service token)
  ↓
Doppler Operator reconciles
  ↓
dk-data-secrets (Kubernetes Secret in dk-data-prod namespace)
  ↓ (env vars via secretKeyRef)
PostgREST pod, Job Trigger pod
```

---

## 4. Network Access Model

### Ingress (external → dk-data)

```
Internet → Traefik (kube-system) → Ingress → postgrest:3000
                                              (dk-data-prod)
```

Only PostgREST is exposed via Ingress. Job Trigger is internal-only.

### Internal (cluster → dk-data)

```
behaviorlabs-prod    → postgrest.dk-data-prod.svc.cluster.local:3000
behaviorlabs-staging → postgrest.dk-data-staging.svc.cluster.local:3000
agentmesh-prod       → postgrest.dk-data-prod.svc.cluster.local:3000
agentmesh-staging    → postgrest.dk-data-staging.svc.cluster.local:3000
```

### Egress (dk-data → shared services)

```
dk-data pods → postgresql.infra.svc.cluster.local:5432  (database)
dk-data pods → alloy.infra.svc.cluster.local:4317       (telemetry)
dk-data pods → kube-dns.kube-system:53                   (DNS)
CronJob pods → external HTTPS APIs (CMS, HRSA, ACC)     (data fetch)
```

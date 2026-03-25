# Research: dk-alchemy Cluster Deployment

**Branch**: `003-alchemy-cluster-deploy` | **Date**: 2026-01-28

## Research Summary

All technical unknowns have been resolved through codebase exploration of both dk-data-fe and dk-alchemy repositories. No external research was needed — the two codebases contain all necessary patterns and conventions.

---

## R1: ArgoCD App-of-Apps Bootstrap Pattern

**Decision**: Follow the exact pattern used by behavior-labs-ai and agent-mesh in dk-alchemy.

**Rationale**: Three existing apps (BehaviorLabs, Agent Mesh, Chemikus) use identical bootstrap structures. Deviating would be inconsistent and unsupported.

**Pattern verified from dk-alchemy**:
- `.gitops/external/<app>.yaml` — Bootstrap Applications (prod + staging) pointing to app repo's `.gitops/{env}/apps`
- `.gitops/repositories/<app>-bootstrap-project.yaml` — Minimal AppProject (only ArgoCD resource types)
- App repo defines full AppProject with RBAC in `.gitops/{env}/apps/project.yaml`
- Bootstrap Applications use `automated: { prune: true, selfHeal: true }`
- Production targets `main` branch; staging targets `staging` branch

**Alternatives considered**:
- ApplicationSet with git directory generator — Rejected: only used for dk-alchemy internal infrastructure, not external apps
- Direct Application creation in dk-alchemy — Rejected: violates separation of concerns; app-specific RBAC belongs in the app repo

---

## R2: Kubernetes Ingress Pattern (Standard Ingress vs IngressRoute)

**Decision**: Replace Traefik IngressRoute CRDs with standard Kubernetes Ingress resources using Traefik annotations.

**Rationale**: All dk-alchemy apps (ArgoCD, Grafana) use standard `networking.k8s.io/v1 Ingress` with Traefik annotations. IngressRoute CRDs are Traefik-specific and not used in the cluster.

**Annotation pattern from dk-alchemy**:
```yaml
annotations:
  cert-manager.io/cluster-issuer: letsencrypt-prod
  traefik.ingress.kubernetes.io/router.entrypoints: websecure
  traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
```

**TLS approach**: Use `cert-manager.io/cluster-issuer: letsencrypt-prod` annotation to auto-provision per-Ingress certificates via DNS-01 challenge. This avoids needing to share wildcard certificate secrets across namespaces.

**Alternatives considered**:
- Reflector operator to mirror wildcard certs — Rejected: adds cross-namespace dependency; per-Ingress certs are simpler
- IngressRoute CRDs with middleware — Rejected: not used by any dk-alchemy app; standard Ingress with annotations is the convention

**Rate limiting**: Traefik `Middleware` CRDs can still be used alongside standard Ingress via `traefik.ingress.kubernetes.io/router.middlewares` annotation. However, Traefik also supports rate limiting via IngressRoute-specific middleware. Since we're using standard Ingress, we'll use the annotation approach to reference middleware resources.

---

## R3: Shared CNPG PostgreSQL Integration

**Decision**: Create a dedicated `dk_data` database within the shared CNPG cluster. Bootstrap via idempotent Kubernetes Job.

**Rationale**: The CNPG cluster at `postgresql.infra.svc.cluster.local:5432` is the single shared database for all dk-alchemy apps. Creating a separate database within the cluster provides data isolation while sharing HA infrastructure (3-replica cluster with sync replication, automated backup to MinIO).

**Connection details verified**:
- Primary (read-write): `postgresql.infra.svc.cluster.local:5432` (or `postgres-rw.infra.svc.cluster.local:5432`)
- Read-only replicas: `postgres-ro.infra.svc.cluster.local:5432`
- Default database: `behavior_labs` (must NOT be used by dk-data-fe)
- PostgreSQL version: 16.4

**Database init Job requirements**:
- Must be idempotent (safe to re-run)
- Creates database `dk_data` if not exists
- Creates roles: `authenticator`, `web_anon`, `analyst`, `api_user`, `readonly`
- Creates schemas: `raw`, `staging`, `mart`, `scoring`, `meta`, `api`
- Applies role grants from existing `002_role_restrictions.sql` migration
- Runs as ArgoCD sync wave 0 (before application deployments at wave 1)

**Alternatives considered**:
- Init container on PostgREST Deployment — Rejected: runs on every pod restart; init Jobs run once
- Manual kubectl exec — Rejected: not version-controlled, not GitOps

---

## R4: Doppler Secret Management Convention

**Decision**: Create dedicated `dk-data` Doppler project with `prd` and `stg` configs.

**Rationale**: dk-alchemy convention uses separate Doppler projects per application. The `dk-infrastructure` project is reserved for shared infrastructure secrets. Application-specific secrets (like JWT secrets, app-specific DB credentials) belong in their own project.

**Naming convention from dk-alchemy**:
- Project: lowercase app name (e.g., `behaviorlabs`, `dk-data`)
- Configs: `prd` (production), `stg` (staging) — NOT `prod`/`stg`
- Token secret name: `doppler-token-secret` (standard across all apps)

**Required secrets in `dk-data` project**:
- `POSTGRES_HOST`: `postgresql.infra.svc.cluster.local`
- `POSTGRES_PORT`: `5432`
- `POSTGRES_USER`: `authenticator`
- `POSTGRES_PASSWORD`: Password for authenticator role
- `POSTGRES_DB`: `dk_data`
- `PGRST_JWT_SECRET`: 256-bit JWT signing secret
- `ANTHROPIC_API_KEY`: Optional, for enrichment service

**Alternatives considered**:
- Reuse `dk-infrastructure` project — Rejected: violates separation; dk-data-specific secrets shouldn't be in the shared infra project
- External Secrets Operator — Rejected: dk-alchemy uses Doppler operator exclusively

---

## R5: NetworkPolicy Namespace References

**Decision**: Reference `kube-system` for Traefik, `infra` for shared services, and named app namespaces for cross-app access.

**Rationale**: Verified from dk-alchemy cluster: Traefik runs in `kube-system` (K3s embedded via HelmChartConfig), not a dedicated namespace. Alloy and PostgreSQL run in `infra`.

**Verified namespace mapping**:
- Traefik: `kube-system`
- PostgreSQL, Redis, Alloy, Grafana: `infra` (prod) / `infra-staging` (staging)
- BehaviorLabs: `behaviorlabs-prod` / `behaviorlabs-staging`
- Agent Mesh: `agentmesh-prod` / `agentmesh-staging`

---

## R6: OTLP Endpoint Configuration

**Decision**: Use `http://alloy.infra.svc.cluster.local:4317` for gRPC OTLP.

**Rationale**: Verified from dk-alchemy: Alloy runs in the `infra` namespace. The current dk-data-fe code uses `alloy.monitoring:4317` which is incorrect. The OpenTelemetry SDK in `observability/__init__.py` uses the `opentelemetry-exporter-otlp` package which defaults to gRPC on port 4317.

**Alternatives considered**:
- HTTP OTLP on port 4318 — Rejected: code already uses gRPC exporter
- Direct push to Mimir/Loki/Tempo — Rejected: Alloy aggregates all telemetry signals

---

## R7: Docker Image Build for Job Trigger

**Decision**: Create a Python 3.11-slim Dockerfile. Build via GitHub Actions on push to `main` and `staging`.

**Rationale**: The Job Trigger is a FastAPI application at `src/dk_data/ingestion/batch/api.py`. It requires the full `dk_data` package (imports from `observability`, `ingestion.utils`, `ingestion.batch`). A multi-stage build minimizes image size.

**Dockerfile requirements verified from codebase**:
- Python 3.11+ (from pyproject.toml `requires-python`)
- Dependencies: fastapi, uvicorn, psycopg2-binary, opentelemetry-*, structlog, prometheus-client, kubernetes, pydantic, requests, pandas
- Entry point: `uvicorn src.dk_data.ingestion.batch.api:app --host 0.0.0.0 --port 8000`
- Build context: repository root (needs access to full `src/dk_data/` tree)
- No `.github/workflows/` exist yet — must be created

**Image registry**: `ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger`
**Tag strategy**: `<branch>-<sha7>` (e.g., `main-a1b2c3d`)

---

## R8: CronJob Migration

**Decision**: Migrate existing CronJob definitions from `.gitops/base/ingestion/` and `.gitops/base/catalog/` to `k8s/base/`.

**Rationale**: The base kustomization references `ingestion/cronjob-cms-all.yaml` and `catalog/cronjob-refresh.yaml`. These must move to the consolidated `k8s/base/` structure.

**CronJob schedules (from existing manifests)**:
- `fetch-cms-all`: Weekly (Sunday 2 AM), 1-hour timeout, 2 retries
- `catalog-refresh`: Daily (6 AM), 10-minute timeout, 2 retries

Both use the Job Trigger container image and inherit the same Doppler-managed secrets.

---

## R9: Manifest Consolidation Strategy

**Decision**: Move all Kubernetes resources to `k8s/base/` with `k8s/overlays/{prod,staging}`. The `.gitops/` directory contains ONLY ArgoCD Application/AppProject definitions.

**Current state** (duplicated/split):
- `.gitops/base/` — Contains deployments, services, configmaps, secrets, observability, cronjobs
- `k8s/postgrest/base/` — Contains IngressRoute and Traefik middleware

**Target state** (consolidated):
```
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── postgrest/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml
│   ├── ingestion/
│   │   ├── job-trigger-deployment.yaml (includes SA, Role, RoleBinding)
│   │   ├── job-trigger-service.yaml
│   │   ├── cronjob-cms-all.yaml
│   │   └── cronjob-refresh.yaml
│   ├── db-init-job.yaml
│   ├── ingress.yaml
│   ├── middleware-rate-limit.yaml
│   ├── networkpolicy.yaml
│   ├── doppler-secret.yaml
│   ├── service-monitor.yaml
│   └── alert-rules.yaml
└── overlays/
    ├── prod/
    │   └── kustomization.yaml
    └── staging/
        └── kustomization.yaml

.gitops/
├── prod/
│   └── apps/
│       ├── kustomization.yaml
│       ├── project.yaml
│       ├── namespace.yaml
│       └── application.yaml
└── staging/
    └── apps/
        ├── kustomization.yaml
        ├── project.yaml
        ├── namespace.yaml
        └── application.yaml
```

**What gets deleted**: `.gitops/base/`, `.gitops/overlays/`, `k8s/postgrest/`

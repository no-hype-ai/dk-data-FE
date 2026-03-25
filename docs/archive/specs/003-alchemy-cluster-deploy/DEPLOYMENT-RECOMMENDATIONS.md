# dk-data-fe Deployment Recommendations

## Overview

This document details what must be resolved to deploy dk-data-fe to the dk-alchemy cluster under `data.behaviorlabs.ai` (production) and `data.preview.behaviorlabs.ai` (preview/staging), integrating with shared infrastructure and making data accessible to other apps.

---

## 1. Critical Architecture Mismatches

### 1.1 Database: Dedicated vs Shared CNPG Cluster

**Current state:** dk-data-fe manifests assume a standalone PostgreSQL instance with its own `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` environment variables from Doppler. The `docker-compose.yml` runs a local Postgres 16 container with database `edwards_tavr`.

**dk-alchemy provides:** A shared CloudNativePG cluster in the `infra` namespace (`postgres-cluster`) bootstrapped with database `behavior_labs`. All apps connect to `postgresql.infra.svc.cluster.local:5432`.

**Resolution required:**
- Decide whether dk-data-fe gets a **dedicated database** within the shared CNPG cluster (e.g., `edwards_tavr` alongside `behavior_labs`) or uses **schemas within `behavior_labs`**.
- **Recommendation:** Create a dedicated database `dk_data` within the shared cluster. This preserves isolation while using the shared HA infrastructure. The CNPG operator supports additional databases via SQL — bootstrap them with a Kubernetes Job or migration.
- Update Doppler secrets so `POSTGRES_HOST` resolves to `postgresql.infra.svc.cluster.local` and `POSTGRES_DB` to `dk_data`.
- The PostgREST `authenticator` role and application roles (`web_anon`, `analyst`, `api_user`) must be created in the shared cluster. These need to be scoped to the `dk_data` database only, not granted access to `behavior_labs`.

### 1.2 Namespace Mismatch

**Current state:** Base kustomization uses namespace `tavr-data`. Overlays patch to `dk-data-fe-dev`, `dk-data-fe-staging`, `dk-data-fe-prod`.

**dk-alchemy convention:** Apps use `<app>-prod` and `<app>-staging` namespaces (e.g., `behaviorlabs-prod`, `agentmesh-prod`).

**Resolution required:**
- Rename namespaces to `dk-data-prod` and `dk-data-staging` (drop the `-fe` suffix for cleaner naming, or keep `dk-data-fe-prod` if preferred).
- Remove the `dev` overlay — dk-alchemy only runs `prod` and `staging` environments on-cluster. Local dev uses docker-compose.

### 1.3 Network Policy: Wrong Namespace Labels

**Current state:** Network policies in dk-data-fe reference `kubernetes.io/metadata.name: traefik` for ingress from the Traefik namespace.

**dk-alchemy reality:** Traefik runs in `kube-system` (K3s embedded Traefik via HelmChartConfig), not a dedicated `traefik` namespace.

**Resolution required:**
- Update all NetworkPolicy `namespaceSelector` for Traefik ingress to match `kubernetes.io/metadata.name: kube-system`.
- Add ingress rules allowing traffic from the `infra` namespace (for shared services accessing dk-data).
- Add ingress rules allowing traffic from other app namespaces that need to query the PostgREST API (e.g., `behaviorlabs-prod`, `agentmesh-prod`).

### 1.4 Observability Endpoint Mismatch

**Current state:** Manifests reference `alloy.monitoring:4317` for the OTLP endpoint.

**dk-alchemy reality:** Alloy runs in the `infra` namespace. The correct endpoint is `alloy.infra.svc.cluster.local:4318` (HTTP OTLP) or port `4317` (gRPC OTLP). The namespace is `infra`, not `monitoring`.

**Resolution required:**
- Update `OTEL_EXPORTER_OTLP_ENDPOINT` to `http://alloy.infra.svc.cluster.local:4317` (gRPC) or `http://alloy.infra.svc.cluster.local:4318` (HTTP).
- Confirm which protocol (gRPC vs HTTP) the OpenTelemetry SDK is configured to use and match the port accordingly.

### 1.5 Doppler Project Mismatch

**Current state:** dk-data-fe DopplerSecret references `project: dk-infrastructure` with configs `prod`, `stg`, `dev`.

**dk-alchemy convention:** `dk-infrastructure` is the shared infrastructure Doppler project (for postgres, redis, minio secrets). Application-specific secrets should live in a dedicated Doppler project.

**Resolution required:**
- Create a dedicated Doppler project `dk-data` (or `dk-data-fe`) with configs `prd` and `stg` (matching dk-alchemy's naming convention of `prd`/`stg`, not `prod`/`stg`).
- Store dk-data-fe-specific secrets there: `POSTGRES_PASSWORD` (for the `authenticator` role), `PGRST_JWT_SECRET`, `ANTHROPIC_API_KEY`.
- For shared infrastructure secrets (like the shared PostgreSQL host), either duplicate them in the dk-data project or reference the shared `dk-infrastructure` project with a second DopplerSecret.

---

## 2. GitOps Restructure (dk-data-fe repo)

The current `.gitops/` directory structure does not match dk-alchemy's external app onboarding pattern. The repo needs a complete restructure.

### 2.1 Required Directory Structure

```
dk-data-fe/
├── .gitops/
│   ├── prod/
│   │   └── apps/
│   │       ├── kustomization.yaml      # Lists all resources below
│   │       ├── project.yaml            # Full AppProject with RBAC
│   │       ├── namespace.yaml          # Namespace: dk-data-prod
│   │       └── application.yaml        # ArgoCD Application → k8s/overlays/prod
│   └── staging/
│       └── apps/
│           ├── kustomization.yaml
│           ├── project.yaml
│           ├── namespace.yaml          # Namespace: dk-data-staging
│           └── application.yaml        # ArgoCD Application → k8s/overlays/staging
├── k8s/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── postgrest/
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   └── configmap.yaml
│   │   ├── ingestion/
│   │   │   ├── job-trigger-deployment.yaml
│   │   │   ├── service.yaml
│   │   │   └── serviceaccount.yaml
│   │   ├── ingress.yaml                # Standard K8s Ingress (not IngressRoute)
│   │   ├── networkpolicy.yaml
│   │   ├── doppler-secret.yaml
│   │   ├── service-monitor.yaml
│   │   └── cronjobs.yaml
│   └── overlays/
│       ├── prod/
│       │   └── kustomization.yaml      # Patches for production
│       └── staging/
│           └── kustomization.yaml      # Patches for staging
└── ... (application source code)
```

### 2.2 Move Away from IngressRoute

**Current state:** dk-data-fe uses Traefik `IngressRoute` CRDs in `k8s/postgrest/base/ingress-route.yaml`.

**dk-alchemy convention:** All apps use standard Kubernetes `Ingress` resources with Traefik annotations. This is more portable and consistent.

**Resolution required:**
- Replace the IngressRoute with a standard `Ingress` resource.
- Use the annotation pattern from dk-alchemy:
  ```yaml
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
  ```
- Reference the shared wildcard TLS certificates (see Section 3).

### 2.3 Consolidate Duplicate Manifests

**Current state:** There are overlapping manifests between `.gitops/base/` and `k8s/postgrest/base/`. The `.gitops/` directory contains full deployment manifests, while `k8s/` contains ingress-related manifests.

**Resolution required:**
- Move all Kubernetes manifests into `k8s/base/` and `k8s/overlays/`.
- The `.gitops/` directory should only contain ArgoCD Application/AppProject definitions.
- Delete the current `.gitops/base/` directory entirely after migrating manifests to `k8s/base/`.

---

## 3. Domain & Ingress Configuration

### 3.1 TLS Certificates

**dk-alchemy already provisions:**
- `wildcard-behaviorlabs-ai-tls` in `behaviorlabs-prod` namespace — covers `*.behaviorlabs.ai`
- `wildcard-preview-behaviorlabs-ai-tls` in `behaviorlabs-staging` namespace — covers `*.preview.behaviorlabs.ai`

**Problem:** These certificates exist in the BehaviorLabs namespaces, not in dk-data's namespaces. dk-data-fe's Ingress resources need access to these TLS secrets.

**Options (pick one):**
1. **Use Reflector** (recommended) — dk-alchemy already has the Reflector operator deployed. Add annotations to the certificate secrets to mirror them into dk-data namespaces:
   ```yaml
   annotations:
     reflector.v1.k8s.emberstack.com/reflection-allowed: "true"
     reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces: "dk-data-prod,dk-data-staging"
   ```
   This requires a patch in dk-alchemy's cert-manager certificates.

2. **Create separate certificates** — Add Certificate resources for dk-data namespaces in dk-alchemy's cert-manager overlay. This duplicates certificates but avoids cross-namespace secret sharing.

3. **Issue certificates in dk-data's Ingress** — Let cert-manager auto-provision certificates via the Ingress annotation `cert-manager.io/cluster-issuer: letsencrypt-prod`. This creates per-Ingress certificates rather than using the wildcards.

### 3.2 Production Ingress (data.behaviorlabs.ai)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: dk-data-api
  namespace: dk-data-prod
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - data.behaviorlabs.ai
      secretName: dk-data-tls  # auto-provisioned by cert-manager
  rules:
    - host: data.behaviorlabs.ai
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: postgrest
                port:
                  number: 3000
          - path: /jobs
            pathType: Prefix
            backend:
              service:
                name: job-trigger
                port:
                  number: 8000
```

### 3.3 Staging Ingress (data.preview.behaviorlabs.ai)

Apply via kustomize overlay patch:
```yaml
- op: replace
  path: /spec/rules/0/host
  value: data.preview.behaviorlabs.ai
- op: replace
  path: /spec/tls/0/hosts/0
  value: data.preview.behaviorlabs.ai
- op: replace
  path: /spec/tls/0/secretName
  value: dk-data-preview-tls
```

### 3.4 DNS Records

**dk-alchemy's DDNS service** already manages `*.behaviorlabs.ai` and `*.preview.behaviorlabs.ai` wildcard DNS records pointing to the cluster. No additional DNS configuration is needed — `data.behaviorlabs.ai` and `data.preview.behaviorlabs.ai` will resolve automatically.

---

## 4. dk-alchemy Changes Required

The following files must be created or modified in the dk-alchemy repository.

### 4.1 Bootstrap Application (new file)

**`.gitops/external/dk-data-fe.yaml`**
```yaml
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dk-data-bootstrap-prod
  namespace: argocd
  labels:
    environment: production
    tenant: dk-data
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: dk-data-bootstrap
  source:
    repoURL: https://github.com/data-kinetic-projects/dk-data-FE.git
    targetRevision: main
    path: .gitops/prod/apps
    directory:
      recurse: false
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dk-data-bootstrap-staging
  namespace: argocd
  labels:
    environment: staging
    tenant: dk-data
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: dk-data-bootstrap
  source:
    repoURL: https://github.com/data-kinetic-projects/dk-data-FE.git
    targetRevision: staging
    path: .gitops/staging/apps
    directory:
      recurse: false
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
```

### 4.2 Bootstrap AppProject (new file)

**`.gitops/repositories/dk-data-bootstrap-project.yaml`**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: dk-data-bootstrap
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  description: Bootstrap project for dk-data-fe (minimal permissions)
  sourceRepos:
    - https://github.com/data-kinetic-projects/dk-data-FE.git
  destinations:
    - namespace: argocd
      server: https://kubernetes.default.svc
  clusterResourceWhitelist: []
  namespaceResourceWhitelist:
    - group: argoproj.io
      kind: Application
    - group: argoproj.io
      kind: ApplicationSet
    - group: argoproj.io
      kind: AppProject
  orphanedResources:
    warn: true
```

### 4.3 Kustomization Updates

**`.gitops/external/kustomization.yaml`** — add `dk-data-fe.yaml` to resources list.

**`.gitops/repositories/kustomization.yaml`** — add `dk-data-bootstrap-project.yaml` to resources list.

### 4.4 PostgreSQL Network Policy Update

**`k8s/infrastructure/postgres/base/networkpolicy.yaml`** — add dk-data namespaces to the ingress allowlist so dk-data pods can connect to the shared PostgreSQL cluster:
```yaml
- from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: dk-data-prod
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: dk-data-staging
  ports:
    - protocol: TCP
      port: 5432
```

### 4.5 Database Initialization

A one-time Job or migration is needed to create the `dk_data` database, the `authenticator` role, and application roles in the shared CNPG cluster. This could be:
- A Kubernetes Job manifest in dk-data-fe's `k8s/base/` that runs `psql` commands
- A SQL migration applied via the Job Trigger service after initial deployment
- Manual `kubectl exec` into a postgres pod (least preferred)

### 4.6 Doppler Token Provisioning

Each dk-data namespace needs a `doppler-token-secret` Kubernetes secret pre-provisioned with a read-only Doppler service token. This is done once per environment:
```bash
kubectl create secret generic doppler-token-secret \
  --namespace dk-data-prod \
  --from-literal=serviceToken=dp.st.prod_xxxx

kubectl create secret generic doppler-token-secret \
  --namespace dk-data-staging \
  --from-literal=serviceToken=dp.st.stg_xxxx
```

---

## 5. Making Data Accessible to Other Apps

### 5.1 Internal Service Access (Cluster DNS)

Other apps in dk-alchemy can access dk-data's PostgREST API via Kubernetes service DNS:

```
http://postgrest.dk-data-prod.svc.cluster.local:3000
http://postgrest.dk-data-staging.svc.cluster.local:3000
```

This requires dk-data-fe's NetworkPolicy to allow ingress from the calling app's namespace.

### 5.2 Direct Database Access

For apps that need direct SQL access (not through PostgREST), they connect to the same shared CNPG cluster but query the `dk_data` database:

```
postgresql://readonly_user:password@postgresql.infra.svc.cluster.local:5432/dk_data
```

Create a `readonly` PostgreSQL role with `SELECT`-only access on the `api` and `mart` schemas. Store credentials in the calling app's Doppler project.

### 5.3 External API Access (via Ingress)

External clients and apps outside the cluster use the public endpoints:

```
https://data.behaviorlabs.ai/          # Production PostgREST API
https://data.preview.behaviorlabs.ai/  # Staging PostgREST API
```

JWT authentication is required for non-public endpoints. The `PGRST_JWT_SECRET` must be shared (via Doppler) with any app that needs to generate tokens.

### 5.4 Recommended Access Patterns by Consumer

| Consumer | Access Method | Auth | Network |
|----------|-------------|------|---------|
| BehaviorLabs API | Internal ClusterIP service | JWT token or none (web_anon) | NetworkPolicy allow from `behaviorlabs-prod` |
| Agent Mesh | Internal ClusterIP service | JWT token | NetworkPolicy allow from `agentmesh-prod` |
| External clients | Public Ingress (data.behaviorlabs.ai) | JWT token | Rate-limited via Traefik middleware |
| BI tools (Grafana) | Direct PostgreSQL via read-only service | PostgreSQL role | Via `postgres-ro.infra.svc.cluster.local` |
| Batch jobs | Direct PostgreSQL | PostgreSQL role | Same namespace |

### 5.5 Cross-App NetworkPolicy Template

For each consuming app, add to dk-data-fe's NetworkPolicy:
```yaml
- from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: behaviorlabs-prod
      podSelector:
        matchLabels:
          app.kubernetes.io/name: api
  ports:
    - protocol: TCP
      port: 3000  # PostgREST
```

---

## 6. Docker Image Build & Registry

### 6.1 Current Gap

No Dockerfile exists for the Job Trigger service. The deployment references `dk-data-fe-job-trigger:latest` but there is no build pipeline.

### 6.2 Required Actions

- Create `Dockerfile` for the Job Trigger / ingestion service (based on Python 3.11).
- Create `Dockerfile.postgrest` only if custom PostgREST configuration is needed beyond environment variables (likely not needed — use the official `postgrest/postgrest:v12.2.3` image).
- Set up GitHub Actions to build and push images to `ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:sha-xxxxx`.
- Update deployment manifests to reference `ghcr.io` image paths.
- dk-alchemy already has GHCR pull credentials distributed via Doppler (`ghcr-secret`). Ensure dk-data namespaces have `imagePullSecrets` referencing this secret.

---

## 7. Observability Integration

### 7.1 Metrics

The ServiceMonitor CRD in dk-data-fe is correctly structured but needs:
- Namespace labels matching dk-alchemy's Alloy scrape configuration
- The `prometheus.io/scrape: "true"` annotation on pods
- Metrics exposed on port `9090` at path `/metrics` (current Job Trigger serves on port `8000` at `/metrics` — verify Alloy discovers this)

### 7.2 Logging

Structured JSON logging via structlog is already implemented. Alloy collects logs from all pods automatically via Kubernetes log discovery. No additional configuration needed.

### 7.3 Tracing

Update the OTLP endpoint from `alloy.monitoring:4317` to `alloy.infra.svc.cluster.local:4317`. The OpenTelemetry SDK in `src/dk_data/observability/` should work as-is once the endpoint is corrected.

### 7.4 Grafana Dashboard

Create a Grafana dashboard JSON in dk-alchemy at `grafana/dashboards/applications/dk-data.json` covering:
- PostgREST request rate, latency, error rate
- Job Trigger execution status and duration
- Data freshness metrics
- PostgreSQL connection pool utilization

### 7.5 Alert Rules

The existing `PrometheusRule` in dk-data-fe can be included in the k8s manifests. Alloy/Mimir will pick it up if the namespace is being scraped.

---

## 8. Items to Resolve Checklist

### Must-Do (Blocking Deployment)

- [ ] **Restructure `.gitops/`** — Move to `prod/apps` and `staging/apps` pattern with AppProject, namespace, and Application definitions
- [ ] **Consolidate k8s manifests** — Merge `.gitops/base/` and `k8s/` into a single `k8s/base/` + `k8s/overlays/` structure
- [ ] **Replace IngressRoute with Ingress** — Use standard Kubernetes Ingress with Traefik annotations, configure `data.behaviorlabs.ai` and `data.preview.behaviorlabs.ai`
- [ ] **Fix namespace naming** — Adopt `dk-data-prod` / `dk-data-staging` (drop `dev` overlay)
- [ ] **Fix Traefik namespace in NetworkPolicy** — Change from `traefik` to `kube-system`
- [ ] **Fix OTLP endpoint** — Change from `alloy.monitoring:4317` to `alloy.infra.svc.cluster.local:4317`
- [ ] **Create Doppler project** — Set up `dk-data` project with `prd`/`stg` configs, populate with PostgreSQL credentials, JWT secret
- [ ] **Create dk-alchemy bootstrap** — Add `.gitops/external/dk-data-fe.yaml`, bootstrap AppProject, update kustomizations
- [ ] **Update dk-alchemy PostgreSQL NetworkPolicy** — Allow dk-data namespaces to connect to shared CNPG cluster
- [ ] **Create database init Job/migration** — Bootstrap `dk_data` database and roles in shared CNPG cluster
- [ ] **Build Job Trigger Docker image** — Create Dockerfile and GitHub Actions pipeline, push to GHCR
- [ ] **Provision Doppler tokens** — Create and apply `doppler-token-secret` in each dk-data namespace
- [ ] **Create `staging` branch** — dk-alchemy bootstraps staging from the `staging` branch, not `main`

### Should-Do (Production Quality)

- [ ] **Add imagePullSecrets** — Reference GHCR credentials in dk-data deployments
- [ ] **Add cross-app NetworkPolicy rules** — Allow BehaviorLabs, Agent Mesh to access PostgREST
- [ ] **Create read-only PostgreSQL role** — For direct database consumers (BI tools, other apps)
- [ ] **Add Grafana dashboard** — Create `dk-data.json` dashboard in dk-alchemy
- [ ] **Add PodDisruptionBudget** — For PostgREST (minAvailable: 1 in prod)
- [ ] **Add pod anti-affinity** — Spread PostgREST replicas across nodes (when cluster scales beyond 1 node)
- [ ] **Document JWT token generation** — For consuming apps that need authenticated PostgREST access
- [ ] **Add health check Ingress path** — Separate unauthenticated `/health` path without rate limiting
- [ ] **Configure CORS origins** — Replace `example.com` placeholders with `behaviorlabs.ai` domains

### Nice-to-Have (Future Improvements)

- [ ] **Add application tests** — No test files exist currently
- [ ] **Add database backup verification** — Automated restore testing
- [ ] **Add load testing baselines** — Know the capacity limits of PostgREST under production load
- [ ] **Add preview environments** — Per-PR ephemeral environments (dk-alchemy pattern supports this in the future)
- [ ] **Add Metabase integration** — Connect to shared PostgreSQL for BI dashboards

---

## 9. Deployment Sequence

The recommended order of operations:

1. **Doppler setup** — Create project, configs, populate secrets, generate service tokens
2. **dk-alchemy changes** — Bootstrap files, AppProject, NetworkPolicy updates, Doppler token secrets
3. **dk-data-fe restructure** — New `.gitops/` layout, consolidated `k8s/` manifests, fixed Ingress
4. **Docker image pipeline** — Dockerfile, GitHub Actions, first image push to GHCR
5. **Database initialization** — Create database, roles, schemas in shared CNPG cluster
6. **Deploy staging first** — Push to `staging` branch, verify ArgoCD sync, test `data.preview.behaviorlabs.ai`
7. **Deploy production** — Merge to `main`, verify ArgoCD sync, test `data.behaviorlabs.ai`
8. **Enable cross-app access** — Update NetworkPolicies, share JWT secret, test from BehaviorLabs API
9. **Observability** — Verify metrics in Grafana, add dashboard, confirm alerts fire correctly

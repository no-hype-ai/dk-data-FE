# Quickstart: dk-alchemy Cluster Deployment

**Branch**: `003-alchemy-cluster-deploy` | **Date**: 2026-01-28

## Prerequisites

Before deploying dk-data-fe to the dk-alchemy cluster:

1. **dk-alchemy cluster** is running with all shared services healthy (ArgoCD, CNPG, Traefik, Doppler operator, cert-manager, Alloy)
2. **Doppler project** `dk-data` exists with `prd` and `stg` configs populated
3. **Doppler service tokens** generated for each config
4. **GHCR credentials** available in the cluster (already provisioned by dk-alchemy)
5. **Repository access** — ArgoCD can reach `github.com/data-kinetic-projects/dk-data-FE`

---

## Step 1: Doppler Setup (Manual, One-Time)

```bash
# Create Doppler project
doppler projects create dk-data

# Set production secrets
doppler secrets set POSTGRES_HOST=postgresql.infra.svc.cluster.local \
  POSTGRES_PORT=5432 \
  POSTGRES_USER=authenticator \
  POSTGRES_PASSWORD=<generate-secure-password> \
  POSTGRES_DB=dk_data \
  PGRST_JWT_SECRET=<generate-256-bit-secret> \
  --project dk-data --config prd

# Set staging secrets (same structure, different values)
doppler secrets set POSTGRES_HOST=postgresql.infra-staging.svc.cluster.local \
  POSTGRES_PORT=5432 \
  POSTGRES_USER=authenticator \
  POSTGRES_PASSWORD=<generate-secure-password> \
  POSTGRES_DB=dk_data \
  PGRST_JWT_SECRET=<generate-256-bit-secret> \
  --project dk-data --config stg

# Generate service tokens
doppler configs tokens create dk-data-prod-token \
  --project dk-data --config prd --plain
doppler configs tokens create dk-data-stg-token \
  --project dk-data --config stg --plain
```

## Step 2: dk-alchemy Bootstrap (One-Time)

In the dk-alchemy repository:

1. Create `.gitops/external/dk-data-fe.yaml` (bootstrap Applications)
2. Create `.gitops/repositories/dk-data-bootstrap-project.yaml` (AppProject)
3. Update `.gitops/external/kustomization.yaml` and `.gitops/repositories/kustomization.yaml`
4. Update `k8s/infrastructure/postgres/base/networkpolicy.yaml` (allow dk-data namespaces)
5. Commit and push to `main`

Then provision Doppler tokens in the cluster:
```bash
# Create namespaces first (ArgoCD will also do this, but tokens need to exist)
kubectl create namespace dk-data-prod
kubectl create namespace dk-data-staging

# Inject Doppler service tokens
kubectl create secret generic doppler-token-secret \
  --namespace dk-data-prod \
  --from-literal=serviceToken=<prod-token-from-step-1>

kubectl create secret generic doppler-token-secret \
  --namespace dk-data-staging \
  --from-literal=serviceToken=<stg-token-from-step-1>
```

## Step 3: Build and Push Job Trigger Image

```bash
# Build locally (or via CI)
docker build -t ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:latest \
  -f Dockerfile .

# Push to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
docker push ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:latest
```

## Step 4: Deploy to Staging

```bash
# Create staging branch from main
git checkout main
git checkout -b staging
git push -u origin staging
```

ArgoCD will:
1. Detect the bootstrap Application for staging
2. Sync the AppProject and Application from `.gitops/staging/apps/`
3. Deploy the database init Job (sync wave 0)
4. Deploy PostgREST and Job Trigger (sync wave 1)

## Step 5: Verify Staging

```bash
# Check ArgoCD sync status
argocd app get dk-data-staging

# Test staging API
curl -v https://data.preview.behaviorlabs.ai/

# Check health
curl https://data.preview.behaviorlabs.ai/health

# Check data catalog (public)
curl https://data.preview.behaviorlabs.ai/data_catalog

# Check authenticated endpoint
TOKEN=$(python3 -c "import jwt; print(jwt.encode({'role':'analyst','exp':9999999999}, '<JWT_SECRET>', algorithm='HS256'))")
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/targets
```

## Step 6: Deploy to Production

```bash
# Merge to main (production auto-syncs)
git checkout main
git merge staging
git push origin main
```

Verify at `https://data.behaviorlabs.ai/`

## Step 7: Verify Cross-App Access

From a BehaviorLabs pod:
```bash
kubectl exec -n behaviorlabs-prod deploy/api -- \
  curl -s http://postgrest.dk-data-prod.svc.cluster.local:3000/data_catalog
```

## Step 8: Verify Observability

1. Open `https://grafana.behaviorlabs.ai`
2. Navigate to Explore → Loki
3. Query: `{namespace="dk-data-prod"}`
4. Verify structured JSON logs appear
5. Navigate to Explore → Mimir
6. Query: `http_requests_total{namespace="dk-data-prod"}`

---

## Local Development

For local development, use docker-compose (no cluster needed):

```bash
# Start all services locally
docker compose up -d

# Access services
# PostgREST: http://localhost:3030
# Job Trigger: http://localhost:8000
# PostgreSQL: localhost:5433

# Run specific Make targets
make health          # Check all service health
make catalog         # View data catalog
make job-list        # List available jobs
make fetch-cms-all   # Trigger full CMS data fetch
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| PostgREST pod CrashLoopBackOff | DB init Job hasn't completed | Check `kubectl get jobs -n dk-data-prod`; ensure db-init succeeded |
| `FATAL: role "authenticator" does not exist` | DB init Job failed | Check Job logs: `kubectl logs job/db-init -n dk-data-prod` |
| DopplerSecret not syncing | Token secret missing or invalid | Verify `kubectl get secret doppler-token-secret -n dk-data-prod` |
| Ingress returns 404 | ArgoCD hasn't synced Ingress | Check `argocd app get dk-data-prod` |
| NetworkPolicy blocking traffic | Namespace not in allowlist | Add namespace to `k8s/base/networkpolicy.yaml` |
| OTLP traces not appearing | Wrong endpoint | Verify `OTEL_EXPORTER_OTLP_ENDPOINT=alloy.infra.svc.cluster.local:4317` |
| CronJob pods failing | Job Trigger image not found | Verify image exists in GHCR and imagePullSecrets are set |

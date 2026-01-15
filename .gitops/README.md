# GitOps Deployment for TAVR Data Platform

This directory contains Kubernetes manifests for deploying the TAVR Data Platform using GitOps principles with Kustomize and ArgoCD.

## Directory Structure

```
.gitops/
├── base/                    # Base Kubernetes resources
│   ├── namespace.yaml       # Namespace definition
│   ├── kustomization.yaml   # Base kustomization
│   ├── postgrest/           # PostgREST API server
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── secret.yaml
│   ├── ingestion/           # Data ingestion components
│   │   ├── cronjob-cms-all.yaml
│   │   ├── job-trigger-deployment.yaml
│   │   └── job-trigger-service.yaml
│   └── catalog/             # Catalog management
│       └── cronjob-refresh.yaml
├── overlays/                # Environment-specific overlays
│   ├── dev/                 # Development environment
│   ├── staging/             # Staging environment
│   └── prod/                # Production environment
│       └── patches/         # Production-specific patches
└── argocd/                  # ArgoCD application manifests
    └── application.yaml
```

## Quick Start

### Local Development (k3s/minikube)

```bash
# Preview what will be deployed
kubectl kustomize .gitops/overlays/dev

# Apply to local cluster
kubectl apply -k .gitops/overlays/dev

# Check deployment status
kubectl get pods -n tavr-data-dev
```

### Staging Deployment

```bash
kubectl apply -k .gitops/overlays/staging
kubectl get pods -n tavr-data-staging
```

### Production Deployment

```bash
# Production uses manual approval - review first
kubectl kustomize .gitops/overlays/prod

# Apply with caution
kubectl apply -k .gitops/overlays/prod
```

## ArgoCD Integration

### Setup ArgoCD Application

1. Ensure ArgoCD is installed in your cluster
2. Update the repository URL in `argocd/application.yaml`
3. Apply the ArgoCD application:

```bash
kubectl apply -f .gitops/argocd/application.yaml -n argocd
```

### Sync Status

```bash
# Check application status
argocd app get tavr-data-platform

# Manual sync (production)
argocd app sync tavr-data-platform-prod
```

## Components

### PostgREST API

Exposes PostgreSQL views as a REST API:

- **Endpoints**: `/catalog`, `/jobs`, `/job_runs`, `/health`, `/targets`, `/hospitals`
- **Port**: 3000 (internal), exposed via Service
- **Authentication**: JWT-based role switching (optional)

### Batch Job System

Automated data ingestion via Kubernetes CronJobs:

| Job | Schedule | Description |
|-----|----------|-------------|
| `fetch-cms-all` | Sunday 2 AM | Fetches all CMS data sources |
| `catalog-refresh` | Daily 6 AM | Updates catalog metadata |

### Job Trigger Service

FastAPI service for manual job triggering:

- **Port**: 8000
- **Endpoints**:
  - `GET /jobs` - List available jobs
  - `POST /jobs/{name}/trigger` - Trigger a job
  - `GET /health` - Health check

## Configuration

### Secrets Management

**Important**: Never commit real secrets. Use one of these approaches:

1. **External Secrets Operator**: Sync from AWS Secrets Manager, Vault, etc.
2. **Sealed Secrets**: Encrypt secrets in Git
3. **SOPS**: Mozilla SOPS for encrypted secrets

Example with External Secrets:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: postgrest-secrets
spec:
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: postgrest-secrets
  data:
    - secretKey: PGRST_DB_URI
      remoteRef:
        key: tavr/postgrest
        property: db_uri
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PGRST_DB_URI` | PostgreSQL connection string | Required |
| `PGRST_DB_SCHEMAS` | Exposed schemas | `api` |
| `PGRST_DB_ANON_ROLE` | Anonymous role | `web_anon` |
| `PGRST_JWT_SECRET` | JWT signing secret | Optional |
| `PGRST_LOG_LEVEL` | Log level | `info` |

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n tavr-data-dev
kubectl describe pod <pod-name> -n tavr-data-dev
kubectl logs <pod-name> -n tavr-data-dev
```

### PostgREST Connection Issues

```bash
# Check PostgREST logs
kubectl logs -l app=postgrest -n tavr-data-dev

# Verify database connectivity
kubectl exec -it <postgrest-pod> -- curl localhost:3000/
```

### CronJob Issues

```bash
# List recent jobs
kubectl get jobs -n tavr-data-dev

# Check job logs
kubectl logs job/<job-name> -n tavr-data-dev
```

## Development

### Testing Changes Locally

```bash
# Build and preview
kubectl kustomize .gitops/overlays/dev

# Dry run
kubectl apply -k .gitops/overlays/dev --dry-run=client

# Apply and watch
kubectl apply -k .gitops/overlays/dev && kubectl get pods -n tavr-data-dev -w
```

### Adding New Resources

1. Add resource YAML to appropriate `base/` subdirectory
2. Reference in `base/kustomization.yaml`
3. Add any environment-specific patches to overlays
4. Test with `kubectl kustomize`

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [src/dk_data/README.md](../src/dk_data/README.md) - Local development
- [specs/001-data-layer-postgrest-gitops/](../specs/001-data-layer-postgrest-gitops/) - Feature specification
